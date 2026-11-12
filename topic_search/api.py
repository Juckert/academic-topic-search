"""HTTP wrapper over SearchPipeline that implements docs/API_CONTRACT.md.

Run: python -m topic_search.api --config configs/search.json
"""

import argparse
import json
import logging
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from topic_search.pipeline import ROOT, SearchPipeline

API_VERSION = "1.0"
API_PREFIX = "/api/v1"
TITLE_LIMIT, ANNOTATION_LIMIT = 500, 3498
METADATA_KEYS = ("year", "department", "program", "work_type", "source_url")
log = logging.getLogger("topic_search.api")


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department: StrictStr | None = Field(default=None, min_length=1, max_length=300)
    year: StrictInt | None = Field(default=None, ge=1900, le=2200)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: StrictStr
    annotation: StrictStr | None = None
    filters: Filters = Filters()

    @field_validator("title")
    @classmethod
    def _title(cls, value):
        value = value.strip()
        if not any(char.isalnum() for char in value) or len(value) > TITLE_LIMIT:
            raise ValueError("invalid title")
        return value

    @field_validator("annotation")
    @classmethod
    def _annotation(cls, value):
        value = value.strip() if value is not None else None
        if value and len(value) > ANNOTATION_LIMIT:
            raise ValueError("annotation too long")
        return value or None


MESSAGES = {
    "title": f"Введите название темы: до {TITLE_LIMIT} символов, хотя бы одна буква или цифра.",
    "annotation": f"Проверьте длину аннотации: до {ANNOTATION_LIMIT} символов.",
    "filters": "Проверьте значения фильтров.",
    None: "Некорректный запрос.",
}


def error(status, code, message, field=None):
    return JSONResponse({"api_version": API_VERSION, "error": {"code": code, "message": message, "field": field}},
                        status_code=status)


def _year(value):
    if type(value) is str and value.strip().isdigit():
        value = int(value.strip())
    return value if type(value) is int and 1900 <= value <= 2200 else None


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    ok = parts.scheme in ("http", "https") and parts.hostname and parts.username is None and parts.password is None
    return value.strip() if ok else None


def public_metadata(metadata):
    """Bring corpus metadata to the contract: all five keys, year as a number, URLs validated."""
    return {"year": _year(metadata.get("year")), "department": _text(metadata.get("department")),
            "program": _text(metadata.get("program")), "work_type": _text(metadata.get("work_type")),
            "source_url": _url(metadata.get("source_url"))}


def dataset_info(config_path):
    profile = json.loads((ROOT / config_path).read_text(encoding="utf-8-sig"))
    corpus = json.loads((ROOT / profile["corpus_config"]).read_text(encoding="utf-8-sig"))
    return (str(corpus.get("dataset_id") or Path(corpus["path"]).stem),
            str(corpus.get("dataset_version") or "unversioned"))


def pipeline_version(pipeline):
    configured = getattr(pipeline, "config", {}).get("pipeline_version")
    return configured or pipeline.method + ("+rerank" if pipeline.reranker is not None else "")


def create_app(config_path="configs/search.json", *, device=None, pipeline=None, dataset=None, frontend_dist=None):
    """Build the app. The pipeline is created once; a load failure is logged and answered with 503."""
    state = {"pipeline": None, "dataset": dataset or ("topics", "unversioned")}
    try:
        if pipeline is None:
            pipeline = SearchPipeline.from_config(config_path, device=device)
            state["dataset"] = dataset or dataset_info(config_path)
        if pipeline.threshold is not None:
            raise ValueError("The API returns the full candidate pool; set threshold to null in the profile")
        state["pipeline"] = pipeline
        log.info("Search profile %s loaded: %s documents, method %s", config_path, len(pipeline.docs), pipeline.method)
    except Exception:
        log.exception("Search pipeline failed to load; API answers 503")
    lock = threading.Lock()

    app = FastAPI(title="Academic Topic Search API", docs_url=None, redoc_url=None, openapi_url=None)
    app.router.redirect_slashes = False

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(API_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        loc = next((e["loc"][1:] for e in exc.errors() if len(e.get("loc", ())) > 1 and e["loc"][0] == "body"), ())
        field = ".".join(str(part) for part in loc if isinstance(part, str)) or None
        if field not in ("title", "annotation", "filters.department", "filters.year"):
            field = "filters" if field and field.startswith("filters") else None
        return error(422, "invalid_request", MESSAGES[field.split(".")[0] if field else None], field)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        # FastAPI answers 400 for a body it cannot decode (e.g. not UTF-8); the contract uses 422.
        if exc.status_code == 400 and request.url.path.startswith(API_PREFIX):
            return error(422, "invalid_request", MESSAGES[None])
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def internal(request, exc):
        log.exception("Unhandled error on %s", request.url.path)
        return error(500, "internal_error", "Внутренняя ошибка сервера. Повторите попытку.")

    def unavailable():
        return error(503, "search_unavailable", "Поиск временно недоступен: корпус или модель не загружены.")

    @app.get(API_PREFIX + "/filters")
    def filters():
        search = state["pipeline"]
        if search is None:
            return unavailable()
        values = [public_metadata(doc.metadata) for doc in search.docs.values()]
        return {"api_version": API_VERSION, "dataset_id": state["dataset"][0], "dataset_version": state["dataset"][1],
                "corpus_size": len(search.docs),
                "departments": sorted({m["department"] for m in values if m["department"] is not None}),
                "years": sorted({m["year"] for m in values if m["year"] is not None}),
                "score_type": search.score_type, "candidate_limit": search.candidate_limit}

    @app.post(API_PREFIX + "/search")
    def search(body: SearchRequest):
        search = state["pipeline"]
        if search is None:
            return unavailable()
        selected = {}
        for name, value in (("department", body.filters.department), ("year", body.filters.year)):
            if value is None:
                continue
            if name not in search.corpus.metadata_fields:
                return error(422, "invalid_request", MESSAGES["filters"], "filters." + name)
            # CSV corpora store years as strings; match both representations.
            selected[name] = [value, str(value)] if name == "year" else value
        text = body.title + ("\n\n" + body.annotation if body.annotation else "")
        with lock:
            result = search.search(text, top_k=search.candidate_limit, filters=selected)
        hits = [{"id": hit["id"], "title": hit["title"],
                 "annotation": search.docs[hit["id"]].annotation,
                 "annotation_origin": search.docs[hit["id"]].annotation_origin,
                 "metadata": public_metadata(hit["metadata"]),
                 "score": hit["score"], "score_type": hit["score_type"],
                 "retrieval_score": hit["retrieval_score"], "retrieval_score_type": hit["retrieval_score_type"]}
                for hit in result["hits"]]
        return {"api_version": API_VERSION, "search_id": uuid.uuid4().hex,
                "query": {"title": body.title, "annotation": body.annotation,
                          "filters": {"department": body.filters.department, "year": body.filters.year}},
                "method": result["method"], "reranker_enabled": result["reranker_enabled"],
                "score_type": result["score_type"],
                "dataset_id": state["dataset"][0], "dataset_version": state["dataset"][1],
                "pipeline_version": pipeline_version(search),
                "corpus_size": result["corpus_size"], "eligible_documents": result["eligible_documents"],
                "candidate_limit": search.candidate_limit, "candidate_count": len(hits),
                "status": result["status"], "empty_reason": result["empty_reason"], "hits": hits}

    if frontend_dist is not None:
        dist = Path(frontend_dist)
        if (dist / "index.html").is_file():
            app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
            log.info("Serving frontend from %s", dist)
        else:
            log.warning("Frontend build not found in %s; only the API is served", dist)
    return app


def main(argv=None):
    import uvicorn
    parser = argparse.ArgumentParser(description="Serve the topic search HTTP API")
    parser.add_argument("--config", default="configs/search.json", help="search profile relative to the project root")
    parser.add_argument("--device", help="override the model device: cpu, cuda:0 or auto")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-dist", default=str(ROOT / "frontend" / "dist"),
                        help="built frontend to serve at /; ignored if it has no index.html")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_app(args.config, device=args.device, frontend_dist=args.frontend_dist)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
