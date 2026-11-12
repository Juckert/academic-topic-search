"""ASGI entry point for uvicorn: uvicorn topic_search.asgi:app --host 0.0.0.0 --port 8000

Settings come from the environment:
  TOPIC_SEARCH_CONFIG         search profile relative to the project root (default configs/search.json)
  TOPIC_SEARCH_DEVICE         optional model device override: cpu, cuda:0 or auto
  TOPIC_SEARCH_FRONTEND_DIST  built frontend served at / (default frontend/dist); empty disables it
"""

import logging
import os

from topic_search.api import create_app
from topic_search.pipeline import ROOT

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_dist = os.environ.get("TOPIC_SEARCH_FRONTEND_DIST", str(ROOT / "frontend" / "dist"))
app = create_app(os.environ.get("TOPIC_SEARCH_CONFIG", "configs/search.json"),
                 device=os.environ.get("TOPIC_SEARCH_DEVICE") or None,
                 frontend_dist=_dist or None)
