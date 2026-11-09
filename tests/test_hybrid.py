import unittest

from baseline.hybrid import reciprocal_rank_fusion


class HybridTests(unittest.TestCase):
    def test_hand_calculated_rrf(self):
        hits = reciprocal_rank_fusion([["a","b"],["b","c"]], k=60)
        self.assertEqual([doc_id for doc_id,_ in hits], ["b","a","c"])
        self.assertAlmostEqual(hits[0][1], 1/62 + 1/61)

    def test_missing_branch_and_empty_lists(self):
        self.assertEqual(reciprocal_rank_fusion([[],["b","a"]]), [("b",1/61),("a",1/62)])
        self.assertEqual(reciprocal_rank_fusion([[],[]]), [])

    def test_ties_and_zero_weights(self):
        self.assertEqual([d for d,_ in reciprocal_rank_fusion([["b"],["a"]])], ["a","b"])
        self.assertEqual(reciprocal_rank_fusion([["b"],["a"]],weights=[0,1]),[("a",1/61)])

    def test_invalid_input_rejected(self):
        for kwargs in ({"k":-1},{"weights":[1]},{"weights":[0,0]},{"weights":[float('nan'),1]}):
            with self.assertRaises(ValueError):
                reciprocal_rank_fusion([["a"],["b"]],**kwargs)
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([["a","a"],["b"]])


if __name__ == "__main__":
    unittest.main()
