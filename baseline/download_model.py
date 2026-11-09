"""Download only pinned public model files; no corpus/query text leaves the machine."""

import os
import argparse

from baseline.io import ROOT, read_json
from baseline.io import digest, dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/dense-e5.json")
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import snapshot_download
    config = read_json(ROOT / args.config)
    dest = ROOT / config["model_dir"]
    files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
             "special_tokens_map.json", "sentencepiece.bpe.model", "README.md"]
    snapshot_download(config["model_id"], revision=config["revision"], token=False,
                      local_dir=str(dest), allow_patterns=files, max_workers=2)
    if any(not (dest / name).is_file() for name in files):
        raise ValueError("Incomplete model download")
    dump(dest / "download_manifest.json", {"model_id": config["model_id"], "revision": config["revision"],
                                          "sha256": {name: digest(dest / name) for name in files}})
    print(f"Pinned model ready at {dest}")


if __name__ == "__main__":
    main()
