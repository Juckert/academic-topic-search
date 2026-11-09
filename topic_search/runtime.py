"""Shared device selection for local embedding and reranking models."""

import os
import re


def resolve_device(requested, torch):
    if not isinstance(requested,str) or not re.fullmatch(r"cpu|auto|cuda(?::\d+)?",requested):
        raise ValueError("device must be cpu, auto, cuda or cuda:<index>")
    if requested == "cpu":
        return torch.device("cpu")
    available = torch.cuda.is_available()
    if requested == "auto" and not available:
        return torch.device("cpu")
    if not available:
        raise ValueError("CUDA requested but unavailable. Install the CUDA PyTorch build and check the NVIDIA driver; see docs/LOCAL_GPU.md")
    index = int(requested.split(":")[1]) if ":" in requested else 0
    if index >= torch.cuda.device_count():
        raise ValueError(f"CUDA device {index} does not exist")
    return torch.device(f"cuda:{index}")


def configure_runtime(config, torch):
    # Must be configured before CUDA matrix multiplications create their handles.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    device = resolve_device(config.get("device","cpu"),torch)
    if type(config.get("threads",4)) is not int or config.get("threads",4) < 1:
        raise ValueError("threads must be a positive integer")
    torch.set_num_threads(config.get("threads",4))
    torch.manual_seed(config.get("seed",42))
    torch.use_deterministic_algorithms(True)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(config.get("seed",42))
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    return device


def runtime_metadata(device, torch):
    result = {"device":str(device),"precision":"float32","torch":torch.__version__,
              "cuda_build":torch.version.cuda}
    if device.type == "cuda":
        result.update(gpu_name=torch.cuda.get_device_name(device),
                      compute_capability=list(torch.cuda.get_device_capability(device)))
    return result
