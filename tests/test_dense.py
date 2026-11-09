import importlib.util
import unittest

AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ("torch", "numpy", "transformers"))


@unittest.skipUnless(AVAILABLE, "Install requirements-dense.txt for dense tests")
class DenseTests(unittest.TestCase):
    def test_cosine_normalization_and_ties(self):
        from baseline.dense import VectorIndex
        index = VectorIndex(["b", "a", "c"], [[4, 0], [2, 0], [0, 3]])
        result = index.search_vector([10, 0])
        self.assertEqual([doc_id for doc_id, _ in result], ["a", "b", "c"])
        self.assertAlmostEqual(result[0][1], 1)
        self.assertAlmostEqual(result[2][1], 0)

    def test_masked_pool_excludes_padding(self):
        import torch
        from baseline.dense import average_pool
        hidden = torch.tensor([[[2., 4.], [4., 8.], [100., 100.]]])
        mask = torch.tensor([[1, 1, 0]])
        self.assertTrue(torch.equal(average_pool(hidden, mask), torch.tensor([[3., 6.]])))

    def test_invalid_vectors_rejected(self):
        from baseline.dense import VectorIndex
        for vectors in ([[0, 0]], [[float("nan"), 1]]):
            with self.assertRaises(ValueError):
                VectorIndex(["a"], vectors)
        with self.assertRaises(ValueError):
            VectorIndex(["a", "a"], [[1, 0], [0, 1]])
        index = VectorIndex(["a"], [[1, 0]])
        with self.assertRaises(ValueError):
            index.search_vector([1, 0, 0])


if __name__ == "__main__":
    unittest.main()
