"""Metrics for externally supplied relevance judgments."""
import math

def metrics(ranks, cutoffs):
    if not ranks:
        raise ValueError("Cannot evaluate an empty query set")
    return {f"{metric}@{k}": sum(
        (1.0 if metric == "hit" else 1.0 / rank) if rank is not None and rank <= k else 0.0
        for rank in ranks) / len(ranks)
        for k in cutoffs for metric in ("hit", "mrr")}

def graded_metrics(ranking, qrels, k=10):
    """Do not treat missing judgments as zero. Recall denominator is known qrels."""
    if k < 1 or len(set(ranking)) != len(ranking):
        raise ValueError("Positive cutoff and unique ranked document IDs required")
    retrieved = ranking[:k]
    unjudged = [doc_id for doc_id in retrieved if doc_id not in qrels]
    positive = {doc_id for doc_id, grade in qrels.items() if grade >= 2}
    result = {"retrieved_count": len(retrieved), "judged_count": len(retrieved) - len(unjudged),
              "unjudged_ids": unjudged, "known_positive_count": len(positive),
              f"ndcg@{k}_known_qrels": None, f"recall@{k}_known_qrels": None}
    if unjudged:
        return result
    gains = sorted((2**grade - 1 for grade in qrels.values()), reverse=True)[:k]
    ideal = sum(gain / math.log2(i + 2) for i, gain in enumerate(gains))
    if ideal:
        actual = sum((2**qrels[doc_id] - 1) / math.log2(i + 2) for i, doc_id in enumerate(retrieved))
        result[f"ndcg@{k}_known_qrels"] = actual / ideal
    if positive:
        result[f"recall@{k}_known_qrels"] = len(set(retrieved) & positive) / len(positive)
    return result
