import tempfile
import unittest
from pathlib import Path

from topic_search.corpus import from_records
from topic_search.pipeline import ROOT, SearchPipeline

try:
    from fastapi.testclient import TestClient
    from topic_search.api import create_app
except ImportError:
    TestClient = None

RETRIEVAL_TYPE = {"bm25": "bm25", "dense": "cosine", "hybrid": "rrf"}
MAPPING = {"id_field": "id", "title_field": "title", "annotation_field": "annotation",
           "annotation_origin_field": "origin",
           "metadata_fields": {"year": "year", "department": "department", "source_url": "url"}}
RECORDS = [
    {"id": "a", "title": "Устойчивость банков", "annotation": "Описание", "origin": "generated",
     "year": 2026, "department": "Финансы", "url": "https://example.org/a"},
    {"id": "b", "title": "Устойчивость российских банков к кризисам", "annotation": None,
     "year": "2025", "department": "Финансы", "url": "javascript:alert(1)"},
    {"id": "c", "title": "Информационная система лаборатории", "annotation": "Текст",
     "year": 2026, "department": "Информатика", "url": None},
]


def assert_contract(case, result, query):
    """Mirror of frontend/src/api.ts validateResult."""
    hits = result["hits"]
    case.assertEqual(result["api_version"], "1.0")
    case.assertEqual(result["query"], query)
    expected = "reranker_logit" if result["reranker_enabled"] else RETRIEVAL_TYPE[result["method"]]
    case.assertEqual(result["score_type"], expected)
    case.assertEqual(len(hits), result["candidate_count"])
    case.assertLessEqual(result["candidate_count"], min(result["candidate_limit"], result["eligible_documents"]))
    case.assertLessEqual(result["eligible_documents"], result["corpus_size"])
    case.assertEqual(result["status"] == "results", bool(hits))
    case.assertEqual(result["empty_reason"] is None, bool(hits))
    case.assertIn(result["empty_reason"], (None, "filters_or_exclusions", "no_candidates"))
    case.assertEqual(len({h["id"] for h in hits}), len(hits))
    for index, hit in enumerate(hits):
        case.assertEqual(hit["score_type"], result["score_type"])
        case.assertEqual(hit["retrieval_score_type"], RETRIEVAL_TYPE[result["method"]])
        case.assertEqual(hit["annotation"] is None, hit["annotation_origin"] == "missing")
        case.assertEqual(set(hit["metadata"]), {"year", "department", "program", "work_type", "source_url"})
        if index:
            case.assertLessEqual(hit["score"], hits[index - 1]["score"])


@unittest.skipIf(TestClient is None, "Install requirements-api.txt for API tests")
class ApiTests(unittest.TestCase):
    def setUp(self):
        pipeline = SearchPipeline(from_records(RECORDS, MAPPING), candidate_limit=50, top_k=5)
        self.client = TestClient(create_app(pipeline=pipeline, dataset=("test", "1")), raise_server_exceptions=False)

    def search(self, title, annotation=None, department=None, year=None):
        body = {"title": title, "annotation": annotation, "filters": {"department": department, "year": year}}
        return self.client.post("/api/v1/search", json=body)

    def test_filters(self):
        response = self.client.get("/api/v1/filters")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json(), {
            "api_version": "1.0", "dataset_id": "test", "dataset_version": "1", "corpus_size": 3,
            "departments": ["Информатика", "Финансы"], "years": [2025, 2026],
            "score_type": "bm25", "candidate_limit": 50})

    def test_search_matches_contract(self):
        response = self.search("  Устойчивость банков ", annotation="   ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        result = response.json()
        query = {"title": "Устойчивость банков", "annotation": None, "filters": {"department": None, "year": None}}
        assert_contract(self, result, query)
        self.assertEqual([h["id"] for h in result["hits"]], ["a", "b"])
        first, second = result["hits"]
        self.assertEqual((first["annotation"], first["annotation_origin"]), ("Описание", "generated"))
        self.assertEqual(first["metadata"]["source_url"], "https://example.org/a")
        self.assertEqual((second["annotation"], second["annotation_origin"]), (None, "missing"))
        self.assertEqual(second["metadata"]["year"], 2025)
        self.assertIsNone(second["metadata"]["source_url"])
        self.assertEqual((result["dataset_id"], result["pipeline_version"]), ("test", "bm25"))

    def test_filters_apply_and_string_years_match(self):
        result = self.search("Устойчивость банков", year=2025).json()
        assert_contract(self, result, {"title": "Устойчивость банков", "annotation": None,
                                       "filters": {"department": None, "year": 2025}})
        self.assertEqual(([h["id"] for h in result["hits"]], result["eligible_documents"]), (["b"], 1))
        empty = self.search("Устойчивость банков", department="Физика").json()
        self.assertEqual((empty["status"], empty["empty_reason"], empty["hits"]), ("empty", "filters_or_exclusions", []))
        none = self.search("Квантовая хромодинамика").json()
        self.assertEqual((none["empty_reason"], none["candidate_count"]), ("no_candidates", 0))

    def test_invalid_requests(self):
        cases = [({"title": "!!!"}, "title"), ({"title": "x" * 501}, "title"),
                 ({"title": "тема", "annotation": "x" * 3499}, "annotation"),
                 ({"title": "тема", "filters": {"year": True}}, "filters.year"),
                 ({"title": "тема", "filters": {"year": "2026"}}, "filters.year"),
                 ({"title": "тема", "filters": {"faculty": "x"}}, "filters"),
                 ({"title": "тема", "extra": 1}, None), ({}, "title")]
        for body, field in cases:
            with self.subTest(body=body):
                response = self.client.post("/api/v1/search", json=body)
                self.assertEqual(response.status_code, 422)
                payload = response.json()
                self.assertEqual((payload["error"]["code"], payload["error"]["field"]), ("invalid_request", field))
                self.assertTrue(payload["error"]["message"])
        broken = self.client.post("/api/v1/search", content=b"{", headers={"Content-Type": "application/json"})
        self.assertEqual((broken.status_code, broken.json()["error"]["field"]), (422, None))
        not_utf8 = self.client.post("/api/v1/search", content=b'{"title":"\xff"}',
                                    headers={"Content-Type": "application/json"})
        self.assertEqual((not_utf8.status_code, not_utf8.json()["error"]["code"]), (422, "invalid_request"))

    def test_unconfigured_filter_field_rejected(self):
        pipeline = SearchPipeline(from_records(RECORDS, {**MAPPING, "metadata_fields": {}}), candidate_limit=5, top_k=5)
        client = TestClient(create_app(pipeline=pipeline))
        response = client.post("/api/v1/search", json={"title": "тема", "filters": {"department": "Финансы"}})
        self.assertEqual((response.status_code, response.json()["error"]["field"]), (422, "filters.department"))

    def test_no_trailing_slash_redirect(self):
        response = self.client.get("/api/v1/filters/", follow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_load_failure_returns_503(self):
        with self.assertLogs("topic_search.api", "ERROR"):
            client = TestClient(create_app("configs/missing-profile.json"))
        for response in (client.get("/api/v1/filters"), client.post("/api/v1/search", json={"title": "тема"})):
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "search_unavailable")

    def test_threshold_profile_rejected(self):
        pipeline = SearchPipeline(from_records(RECORDS, MAPPING), candidate_limit=5, top_k=5,
                                  threshold={"score_type": "bm25", "value": 1})
        with self.assertLogs("topic_search.api", "ERROR"):
            app = create_app(pipeline=pipeline)
        self.assertEqual(TestClient(app).get("/api/v1/filters").status_code, 503)

    def test_internal_error_hides_details(self):
        pipeline = SearchPipeline(from_records(RECORDS, MAPPING), candidate_limit=5, top_k=5)
        pipeline.search = lambda *args, **kwargs: 1 / 0
        client = TestClient(create_app(pipeline=pipeline), raise_server_exceptions=False)
        with self.assertLogs("topic_search.api", "ERROR"):
            response = client.post("/api/v1/search", json={"title": "тема"})
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (500, "internal_error"))
        self.assertNotIn("ZeroDivision", response.text)

    def test_serves_frontend_build(self):
        cache = ROOT / ".cache" / "tests"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            (Path(directory) / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
            pipeline = SearchPipeline(from_records(RECORDS, MAPPING), candidate_limit=5, top_k=5)
            client = TestClient(create_app(pipeline=pipeline, frontend_dist=directory))
            self.assertIn("<title>app</title>", client.get("/").text)
            self.assertEqual(client.get("/api/v1/filters").status_code, 200)


if __name__ == "__main__":
    unittest.main()
