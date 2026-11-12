"""Build the frontend in API mode and serve it together with the search API.

python -m scripts.serve [--skip-build] [--config configs/search.json] [--host 127.0.0.1] [--port 8000]

The server itself is a regular ASGI app: once frontend/dist is built, it can be run
directly with `uvicorn topic_search.asgi:app` (see docs/DEPLOY.md).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_frontend():
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found: install Node.js 22.12+ or pass --skip-build")
    env = {**os.environ, "VITE_SEARCH_MODE": "api"}
    for command in (["ci", "--ignore-scripts"], ["run", "build"]):
        try:
            subprocess.run([npm, *command], cwd=ROOT / "frontend", env=env, check=True)
        except subprocess.CalledProcessError as error:
            sys.exit(f"npm {' '.join(command)} failed with exit code {error.returncode}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the frontend and serve it with the search API")
    parser.add_argument("--skip-build", action="store_true", help="serve the existing frontend/dist or only the API")
    parser.add_argument("--config", default="configs/search.json", help="search profile relative to the project root")
    parser.add_argument("--device", help="override the model device: cpu, cuda:0 or auto")
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to accept external connections")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not args.skip_build:
        build_frontend()
    os.environ["TOPIC_SEARCH_CONFIG"] = args.config
    if args.device:
        os.environ["TOPIC_SEARCH_DEVICE"] = args.device
    import uvicorn
    uvicorn.run("topic_search.asgi:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
