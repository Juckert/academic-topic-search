"""Long-lived search service: filters -> candidates -> optional rerank -> threshold -> top-k."""

import json
import math
from pathlib import Path

from baseline.hybrid import reciprocal_rank_fusion
from baseline.search import BM25
from topic_search.corpus import load_corpus

ROOT = Path(__file__).resolve().parents[1]


class SearchPipeline:
    def __init__(self, corpus, method="bm25", candidate_limit=50, top_k=5,
                 bm25_config=None, dense=None, reranker=None, rrf_config=None, threshold=None):
        if method not in ("bm25", "dense", "hybrid"):
            raise ValueError("method must be bm25, dense or hybrid")
        if type(candidate_limit) is not int or type(top_k) is not int or not 1 <= top_k <= candidate_limit:
            raise ValueError("Require 1 <= top_k <= candidate_limit, both integers")
        if method in ("dense", "hybrid") and dense is None:
            raise ValueError("Dense backend required")
        self.corpus = corpus
        self.docs = {d.id:d for d in corpus.topics}
        if not self.docs or len(self.docs) != len(corpus.topics):
            raise ValueError("Nonempty corpus with unique IDs required")
        self.method, self.candidate_limit, self.top_k = method, candidate_limit, top_k
        self.dense, self.reranker = dense, reranker
        self.rrf = rrf_config or {"rrf_k":60,"candidate_depth":50,"weights":[1,1]}
        if method == "hybrid":
            if type(self.rrf["candidate_depth"]) is not int or self.rrf["candidate_depth"] < candidate_limit:
                raise ValueError("RRF candidate_depth must be >= candidate_limit")
            reciprocal_rank_fusion([[],[]], self.rrf["rrf_k"], self.rrf["weights"])
        self.retrieval_score_type = {"bm25":"bm25", "dense":"cosine", "hybrid":"rrf"}[method]
        self.score_type = reranker.score_type if reranker else self.retrieval_score_type
        self.threshold = self._threshold(threshold)
        config = bm25_config or {"k1":1.5,"b":0.75}
        self.bm25 = BM25([(d.id,d.text) for d in corpus.topics],config["k1"],config["b"]) if method in ("bm25","hybrid") else None

    @classmethod
    def from_config(cls, config_path="configs/search.json", *, device=None):
        def read(path):
            return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))
        config = read(config_path)
        device_override = device if device is not None else config.get("device")
        def model_config(path):
            model = read(path)
            if device_override is not None:
                model["device"] = device_override
            return model
        corpus = load_corpus(read(config["corpus_config"]), ROOT)
        method = config["method"]
        if method not in ("bm25", "dense", "hybrid"):
            raise ValueError("Unknown retrieval method")
        dense = None
        if method in ("dense", "hybrid"):
            from baseline.dense import DenseSearch
            dense = DenseSearch([(d.id,d.text) for d in corpus.topics], model_config(config["dense_config"]))
        reranker = None
        if config.get("reranker_config"):
            from topic_search.rerank import CrossEncoderReranker
            reranker = CrossEncoderReranker(model_config(config["reranker_config"]), ROOT)
        if device_override is not None and dense is None and reranker is None:
            raise ValueError("device selects model execution; this BM25-only profile has no neural model")
        instance = cls(corpus, method, config["candidate_limit"], config["top_k"],
                       read(config["bm25_config"]), dense, reranker,
                       read(config["rrf_config"]) if method == "hybrid" else None, config.get("threshold"))
        instance.config = config
        return instance

    def runtime_info(self):
        return {"embedding_device":str(self.dense.device) if self.dense is not None and hasattr(self.dense,"device") else None,
                "reranker_device":str(self.reranker.device) if self.reranker is not None and hasattr(self.reranker,"device") else None,
                "vector_search_device":"cpu" if self.dense is not None else None}

    def _threshold(self, threshold):
        if threshold is None:
            return None
        if not isinstance(threshold, dict) or set(threshold) != {"score_type", "value"}:
            raise ValueError("Threshold must contain score_type and value")
        if threshold["score_type"] != self.score_type:
            raise ValueError(f"Threshold must use {self.score_type}, not another score scale")
        value = threshold["value"]
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError("Threshold value must be finite")
        return dict(threshold)

    def _eligible(self, filters, exclude_ids):
        if not isinstance(filters, dict) or any(key not in self.corpus.metadata_fields for key in filters):
            raise ValueError("Filters must use configured metadata fields")
        for values in filters.values():
            values = values if isinstance(values,list) else [values]
            if not values or any(v is not None and type(v) not in (str,int,float,bool) for v in values):
                raise ValueError("Filter values must be scalars or nonempty scalar lists")
            if any(type(v) is float and not math.isfinite(v) for v in values):
                raise ValueError("Filter numbers must be finite")
        if not isinstance(exclude_ids,(list,tuple,set)) or any(not isinstance(i,str) for i in exclude_ids):
            raise ValueError("exclude_ids must be a collection of string IDs")
        excluded = set(exclude_ids)
        return {d.id for d in self.corpus.topics if d.id not in excluded and
                all(d.metadata.get(key) in (value if isinstance(value,list) else [value]) for key,value in filters.items())}

    def _retrieve(self, query, eligible):
        def branch(backend):
            # Search the complete index before applying metadata/exclusion constraints.
            # This avoids losing eligible matches outside an unfiltered top-k.
            hits = backend.search(query, len(self.docs))
            if len({doc_id for doc_id,_ in hits}) != len(hits):
                raise ValueError("Retriever returned duplicate IDs")
            if any(doc_id not in self.docs or not math.isfinite(score) for doc_id,score in hits):
                raise ValueError("Retriever returned unknown IDs or invalid scores")
            return sorted([(i,float(s)) for i,s in hits if i in eligible],key=lambda h:(-h[1],h[0]))
        if self.method == "hybrid":
            depth = self.rrf["candidate_depth"]
            lists = [[i for i,_ in branch(backend)[:depth]] for backend in (self.bm25,self.dense)]
            return reciprocal_rank_fusion(lists,self.rrf["rrf_k"],self.rrf["weights"],self.candidate_limit)
        return branch(self.bm25 if self.method == "bm25" else self.dense)[:self.candidate_limit]

    def search(self, query, *, top_k=None, filters=None, exclude_ids=None, threshold=None):
        if not isinstance(query,str) or not any(char.isalnum() for char in query):
            raise ValueError("Query must contain letters or digits")
        query = query.strip()
        if len(query) > 4000:
            raise ValueError("Query must not exceed 4000 characters")
        top_k = self.top_k if top_k is None else top_k
        if type(top_k) is not int or not 1 <= top_k <= self.candidate_limit:
            raise ValueError("top_k must be between 1 and candidate_limit")
        applied_threshold = self.threshold if threshold is None else self._threshold(threshold)
        filters = {} if filters is None else filters
        eligible = self._eligible(filters, [] if exclude_ids is None else exclude_ids)
        candidates = self._retrieve(query, eligible) if eligible else []
        if self.reranker and candidates:
            scores = self.reranker.score(query,[self.docs[doc_id].text for doc_id,_ in candidates])
            if len(scores) != len(candidates) or not all(math.isfinite(s) for s in scores):
                raise ValueError("Reranker must return one finite score per candidate")
        else:
            scores = [score for _,score in candidates]
        hits = [{"id":doc_id,"title":self.docs[doc_id].title,"metadata":dict(self.docs[doc_id].metadata),
                 "score":float(score),"score_type":self.score_type,
                 "retrieval_score":retrieval_score,"retrieval_score_type":self.retrieval_score_type}
                for (doc_id,retrieval_score),score in zip(candidates,scores)]
        hits.sort(key=lambda hit:(-hit["score"],hit["id"]))
        if applied_threshold is not None:
            hits = [hit for hit in hits if hit["score"] >= applied_threshold["value"]]
        reason = None if hits else "filters_or_exclusions" if not eligible else "no_candidates" if not candidates else "below_threshold"
        return {"query":query,"method":self.method,"reranker_enabled":self.reranker is not None,
                "status":"results" if hits else "empty", "empty_reason":reason,
                "score_type":self.score_type,"threshold":applied_threshold,
                "corpus_size":len(self.docs),"eligible_documents":len(eligible),
                "candidate_count":len(candidates),"passing_threshold_count":len(hits),
                "hits":hits[:top_k]}
