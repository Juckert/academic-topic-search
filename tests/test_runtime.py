import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from topic_search.runtime import resolve_device


class RuntimeTests(unittest.TestCase):
    def torch(self,available=False,count=0):
        return SimpleNamespace(device=lambda name:name,cuda=SimpleNamespace(
            is_available=Mock(return_value=available),device_count=Mock(return_value=count)))

    def test_cpu_does_not_probe_cuda(self):
        module=self.torch()
        self.assertEqual(resolve_device("cpu",module),"cpu")
        module.cuda.is_available.assert_not_called()

    def test_auto_falls_back_to_cpu(self):
        self.assertEqual(resolve_device("auto",self.torch()),"cpu")

    def test_auto_selects_first_available_gpu(self):
        self.assertEqual(resolve_device("auto",self.torch(True,2)),"cuda:0")

    def test_explicit_gpu_never_silently_falls_back(self):
        with self.assertRaisesRegex(ValueError,"CUDA requested"):
            resolve_device("cuda",self.torch())

    def test_specific_gpu_and_invalid_index(self):
        self.assertEqual(resolve_device("cuda:1",self.torch(True,2)),"cuda:1")
        with self.assertRaisesRegex(ValueError,"does not exist"):
            resolve_device("cuda:2",self.torch(True,2))

    def test_invalid_device_syntax(self):
        for value in (None,"gpu","cuda:-1","cpu:0","cuda:x"):
            with self.assertRaises(ValueError):resolve_device(value,self.torch())


if __name__ == "__main__":
    unittest.main()
