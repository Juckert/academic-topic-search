"""Local cross-encoder scoring of query/document pairs; raw logits, not probabilities."""

import math


class CrossEncoderReranker:
    score_type = "reranker_logit"

    def __init__(self, config, root):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from baseline.io import read_json
        from baseline.io import digest
        from topic_search.runtime import configure_runtime
        if config["score_type"] != self.score_type:
            raise ValueError("Reranker expects raw logits")
        if config["batch_size"] < 1 or config["max_length"] < 1:
            raise ValueError("Positive batch size and max length required")
        self.config = config
        self.torch = torch
        self.device = configure_runtime(config,torch)
        model_dir = root / config["model_dir"]
        manifest = read_json(model_dir / "download_manifest.json")
        if any(manifest[key] != config[key] for key in ("model_id", "revision")):
            raise ValueError("Reranker revision mismatch")
        for name, expected in manifest["sha256"].items():
            if digest(model_dir / name) != expected:
                raise ValueError(f"Reranker file hash mismatch: {name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False, use_safetensors=True, attn_implementation="eager")
        if self.model.config.num_labels != 1:
            raise ValueError("Expected a single-logit ranking model")
        self.model.to(device=self.device,dtype=torch.float32)
        self.model.eval()

    def score(self, query, texts):
        scores = []
        for offset in range(0, len(texts), self.config["batch_size"]):
            batch_texts = texts[offset:offset+self.config["batch_size"]]
            batch = self.tokenizer([query]*len(batch_texts), batch_texts, padding=True, truncation=True,
                                   max_length=self.config["max_length"], return_tensors="pt")
            batch = {name:value.to(self.device) for name,value in batch.items()}
            with self.torch.inference_mode():
                logits = self.model(**batch).logits[:,0]
            scores.extend(float(value) for value in logits.cpu().tolist())
        if len(scores) != len(texts) or not all(math.isfinite(score) for score in scores):
            raise ValueError("Reranker returned invalid scores")
        return scores
