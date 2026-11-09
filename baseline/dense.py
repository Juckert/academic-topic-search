"""Frozen multilingual E5 on CPU/CUDA; exact cosine retrieval on CPU."""

import os
import time

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from baseline.io import ROOT, read_json
from baseline.io import digest
from topic_search.runtime import configure_runtime, runtime_metadata


def average_pool(hidden, attention_mask):
    masked = hidden.masked_fill(~attention_mask[..., None].bool(), 0.0)
    return masked.sum(dim=1) / attention_mask.sum(dim=1)[..., None].clamp(min=1)


class VectorIndex:
    def __init__(self, doc_ids, vectors):
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or not len(doc_ids) or matrix.shape[0] != len(doc_ids):
            raise ValueError("Nonempty document IDs and matching 2D vectors required")
        if len(set(doc_ids)) != len(doc_ids) or not np.isfinite(matrix).all():
            raise ValueError("Unique IDs and finite vectors required")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("Zero document vector")
        self.doc_ids = list(doc_ids)
        self.vectors = matrix / norms

    def search_vector(self, vector, limit=10):
        query = np.asarray(vector, dtype=np.float32)
        if limit < 1 or query.shape != (self.vectors.shape[1],) or not np.isfinite(query).all():
            raise ValueError("Positive limit and finite query of matching dimension required")
        norm = np.linalg.norm(query)
        if norm == 0:
            raise ValueError("Zero query vector")
        scores = self.vectors @ (query / norm)
        return sorted(zip(self.doc_ids, map(float, scores)), key=lambda pair: (-pair[1], pair[0]))[:limit]


class DenseSearch:
    def __init__(self, documents, config):
        if config["pooling"] != "attention_mask_mean" or not config["normalize"]:
            raise ValueError("Normalized mean pooling is required")
        if config["search"] != "exact_cosine":
            raise ValueError("Only exact cosine search supported")
        self.config = config
        self.query_encoding_ms = 0.0
        self.ranking_ms = 0.0
        self.query_count = 0
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        self.device = configure_runtime(config,torch)
        model_dir = ROOT / config["model_dir"]
        manifest_path = model_dir / "download_manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Run python -m baseline.download_model first")
        self.model_manifest = read_json(manifest_path)
        if any(self.model_manifest[key] != config[key] for key in ("model_id", "revision")):
            raise ValueError("Downloaded model revision differs from model config")
        for name, expected in self.model_manifest["sha256"].items():
            if digest(model_dir / name) != expected:
                raise ValueError(f"Model file hash mismatch: {name}")
        start = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False,
                                              use_safetensors=True, attn_implementation="eager")
        self.model.to(device=self.device,dtype=torch.float32)
        self.model.eval()
        self.load_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        vectors = self.encode([text for _, text in documents], config["document_prefix"])
        self.index = VectorIndex([doc_id for doc_id, _ in documents], vectors)
        self.index_ms = (time.perf_counter() - start) * 1000

    def encode(self, texts, prefix):
        chunks = []
        for start in range(0, len(texts), self.config["batch_size"]):
            inputs = [prefix + text for text in texts[start:start + self.config["batch_size"]]]
            batch = self.tokenizer(inputs, max_length=self.config["max_length"], padding=True,
                                   truncation=True, return_tensors="pt")
            batch = {name:value.to(self.device) for name,value in batch.items()}
            with torch.inference_mode():
                hidden = self.model(**batch).last_hidden_state
                pooled = average_pool(hidden, batch["attention_mask"])
                vectors = torch.nn.functional.normalize(pooled, p=2, dim=1)
            chunks.append(vectors.cpu().numpy())
        if not chunks:
            raise ValueError("Cannot encode empty batch")
        output = np.concatenate(chunks)
        if output.shape[1] != self.config["dimensions"] or not np.isfinite(output).all():
            raise ValueError("Unexpected embedding shape or nonfinite values")
        return output

    def search(self, query, limit=10):
        if not query.strip():
            return []
        start = time.perf_counter()
        vector = self.encode([query], self.config["query_prefix"])[0]
        self.query_encoding_ms += (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        hits = self.index.search_vector(vector, limit)
        self.ranking_ms += (time.perf_counter() - start) * 1000
        self.query_count += 1
        return hits

    def metadata(self):
        return {"model_files": self.model_manifest, "model_load_ms": self.load_ms,
                "index_ms": self.index_ms, "query_encoding_total_ms": self.query_encoding_ms,
                "ranking_total_ms": self.ranking_ms, "query_count": self.query_count,
                "timing_note": "Single sequential run; query timing includes device-to-host transfer; no throughput benchmark",
                "runtime": runtime_metadata(self.device,torch),
                "torch": torch.__version__, "numpy": np.__version__}
