"""Reciprocal Rank Fusion of fixed BM25 and E5 candidate lists."""

import math
from collections import defaultdict

from baseline.search import BM25


def reciprocal_rank_fusion(rankings, k=60, weights=None, limit=10):
    if not math.isfinite(k) or k < 0 or type(limit) is not int or limit < 1:
        raise ValueError("Nonnegative finite k and positive integer limit required")
    weights = [1.0] * len(rankings) if weights is None else weights
    if len(weights) != len(rankings) or not weights or any(not math.isfinite(w) or w < 0 for w in weights) or not any(weights):
        raise ValueError("Nonnegative finite weights matching rankings, with at least one positive weight, required")
    scores = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        if len(set(ranking)) != len(ranking):
            raise ValueError("Duplicate document ID within a ranking")
        if weight == 0:
            continue
        for rank, doc_id in enumerate(ranking, 1):
            scores[doc_id] += weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]


class HybridSearch:
    def __init__(self, documents, bm25_config, dense_config, config):
        from baseline.dense import DenseSearch
        if type(config["candidate_depth"]) is not int or config["candidate_depth"] < 1:
            raise ValueError("Positive integer candidate depth required")
        if config["tie_break"] != "document_id_ascending":
            raise ValueError("Unsupported tie breaker")
        reciprocal_rank_fusion([[], []], config["rrf_k"], config["weights"])
        self.config = config
        self.bm25 = BM25(documents, bm25_config["k1"], bm25_config["b"])
        self.dense = DenseSearch(documents, dense_config)
        self.last_trace = None

    def search(self, query, limit=10):
        depth = self.config["candidate_depth"]
        if limit > depth:
            raise ValueError("Output cutoff cannot exceed configured candidate depth")
        lexical, semantic = self.bm25.search(query, depth), self.dense.search(query, depth)
        lists = [[doc_id for doc_id, _ in hits] for hits in (lexical, semantic)]
        merged = reciprocal_rank_fusion(lists, self.config["rrf_k"], self.config["weights"], limit)
        self.last_trace = {
            "bm25_candidates": [{"doc_id":doc_id,"rank":rank,"score":score} for rank,(doc_id,score) in enumerate(lexical,1)],
            "dense_candidates": [{"doc_id":doc_id,"rank":rank,"score":score} for rank,(doc_id,score) in enumerate(semantic,1)],
            "union_size":len(set(lists[0]) | set(lists[1]))}
        return merged

    def metadata(self):
        return {"dense":self.dense.metadata(),"fusion_config":self.config,
                "note":"Sequential BM25 + E5 retrieval; RRF uses ranks only, not component scores"}
