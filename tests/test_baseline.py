import math
import unittest

from baseline.evaluate import metrics
from baseline.search import BM25, tokenize


class BaselineTests(unittest.TestCase):
    def test_unicode_normalization(self):
        self.assertEqual(tokenize("Ёлка, LLM-2026_тест!"), ["елка", "llm", "2026", "тест"])

    def test_hand_calculated_bm25(self):
        index = BM25([("a", "кот кот"), ("b", "пес")])
        score = index.search("кот")[0][1]
        expected = math.log(2) * 2 * 2.5 / (2 + 1.5 * (0.25 + 0.75 * 2 / 1.5))
        self.assertAlmostEqual(score, expected)

    def test_empty_unknown_and_ties(self):
        index = BM25([("b", "кот"), ("a", "кот")])
        self.assertEqual(index.search("рыба"), [])
        self.assertEqual(index.search("!!!"), [])
        self.assertEqual([i for i, _ in index.search("кот")], ["a", "b"])
        self.assertEqual(index.search("кот кот"), index.search("кот"))

    def test_metrics_missing_and_cutoffs(self):
        actual = metrics([1, 2, None, 11], [1, 10])
        self.assertEqual(actual["hit@1"], 0.25)
        self.assertEqual(actual["hit@10"], 0.5)
        self.assertEqual(actual["mrr@10"], 0.375)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            BM25([("a", "кот"), ("a", "пес")])


if __name__ == "__main__":
    unittest.main()
