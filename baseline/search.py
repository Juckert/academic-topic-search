"""BM25 with positive Robertson IDF and deterministic document-ID tie breaks."""

import math
import re
import unicodedata
from collections import Counter, defaultdict


def tokenize(text):
    """NFKC, lowercase, ё -> е, Unicode letters/digits; no stemming."""
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).lower().replace("ё", "е"))


class BM25:
    def __init__(self, documents, k1=1.5, b=0.75):
        if not documents or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Nonempty corpus, k1 > 0 and 0 <= b <= 1 required")
        self.k1, self.b = k1, b
        self.lengths = {}
        self.postings = defaultdict(list)
        for doc_id, text in documents:
            if doc_id in self.lengths:
                raise ValueError(f"Duplicate document ID: {doc_id}")
            terms = Counter(tokenize(text))
            self.lengths[doc_id] = sum(terms.values())
            for term, frequency in terms.items():
                self.postings[term].append((doc_id, frequency))
        self.average_length = sum(self.lengths.values()) / len(self.lengths)
        if not self.average_length:
            raise ValueError("Corpus has no tokens")
        self.idf = {term: math.log(1 + (len(self.lengths) - len(items) + 0.5) / (len(items) + 0.5))
                    for term, items in self.postings.items()}

    def search(self, query, limit=10):
        if limit < 1:
            raise ValueError("limit must be positive")
        scores = defaultdict(float)
        # Each unique query term contributes once; query term frequency is ignored.
        for term in sorted(set(tokenize(query))):
            for doc_id, frequency in self.postings.get(term, ()):
                length_factor = 1 - self.b + self.b * self.lengths[doc_id] / self.average_length
                scores[doc_id] += self.idf[term] * frequency * (self.k1 + 1) / (frequency + self.k1 * length_factor)
        # No arbitrary zero-score documents for queries with no lexical overlap.
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
