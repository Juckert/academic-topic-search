"""Check actual local Torch execution; optional end-to-end model check."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device",default="auto")
    parser.add_argument("--full",action="store_true",help="Load embedding and reranker and execute a search")
    parser.add_argument("--config",default="configs/search-rerank.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    import torch
    from topic_search.runtime import configure_runtime, runtime_metadata
    report = {"requested_device":args.device,"cuda_available":torch.cuda.is_available(),
              "gpu_execution_tested":False,"full_model_check":False}
    try:
        device = configure_runtime({"device":args.device,"threads":4,"seed":42},torch)
        report.update(runtime_metadata(device,torch))
        left = torch.arange(128*128,dtype=torch.float32,device=device).reshape(128,128)/1000
        actual = left @ left.T
        if not torch.isfinite(actual).all().item():
            raise ValueError("Matrix computation produced nonfinite results")
        expected = left.cpu() @ left.cpu().T
        torch.testing.assert_close(actual.cpu(),expected,rtol=1e-4,atol=1e-3)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
            report["gpu_execution_tested"] = True
            report["torch_cuda_arch_list"] = torch.cuda.get_arch_list()
        if args.full:
            from topic_search import SearchPipeline
            service = SearchPipeline.from_config(args.config,device=str(device))
            models = [backend for backend in (service.dense,service.reranker) if backend is not None]
            if not models:
                raise ValueError("Full check requires a neural-model profile")
            for backend in models:
                if next(backend.model.parameters()).device != device:
                    raise ValueError("Model parameters are on the wrong device")
            answer = service.search("Поиск разовой работы через приложение",top_k=3)
            if not answer["hits"]:
                raise ValueError("Full-model smoke query returned no results")
            report.update(full_model_check=True,runtime=service.runtime_info(),returned_hits=len(answer["hits"]))
        report["status"] = "passed"
    except (ValueError,RuntimeError,OSError,AssertionError) as exc:
        report.update(status="failed",error=str(exc))
    encoded=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
    print(encoded)
    if args.output:
        path=Path(args.output)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(encoded,encoding="utf-8")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
