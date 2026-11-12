import json
import tempfile
import unittest
from pathlib import Path

from topic_search.corpus import from_records, load_corpus
from topic_search.pipeline import ROOT, SearchPipeline


class FakeDense:
    def search(self, query, limit):
        return [("a",0.9),("b",0.8),("c",0.7)][:limit]


class FakeReranker:
    score_type = "reranker_logit"
    def score(self, query, texts):
        return [{"альфа":-4,"бета":3,"гамма":1}[text] for text in texts]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"id_field":"key","title_field":"name","metadata_fields":{"year":"date"}}
        self.records = [{"key":"a","name":"альфа","date":2025},
                        {"key":"b","name":"бета","date":2026},
                        {"key":"c","name":"гамма","date":2026}]
        self.corpus = from_records(self.records,self.mapping)

    def test_metadata_filter_before_candidate_cutoff(self):
        service = SearchPipeline(self.corpus,method="dense",dense=FakeDense(),candidate_limit=1,top_k=1)
        result = service.search("тема",filters={"year":2026})
        self.assertEqual(result["hits"][0]["id"],"b")
        self.assertEqual(result["eligible_documents"],2)

    def test_exclude_before_cutoff_and_no_filter_results(self):
        service = SearchPipeline(self.corpus,method="dense",dense=FakeDense(),candidate_limit=1,top_k=1)
        self.assertEqual(service.search("тема",exclude_ids=["a"])["hits"][0]["id"],"b")
        result=service.search("тема",filters={"year":2027})
        self.assertEqual(result["empty_reason"],"filters_or_exclusions")
        self.assertEqual(result["candidate_count"],0)

    def test_rerank_then_threshold_then_top_k(self):
        service=SearchPipeline(self.corpus,method="dense",dense=FakeDense(),reranker=FakeReranker(),candidate_limit=3,top_k=1)
        result=service.search("тема",threshold={"score_type":"reranker_logit","value":2})
        self.assertEqual([h["id"] for h in result["hits"]],["b"])
        self.assertEqual(result["hits"][0]["retrieval_score"],0.8)
        self.assertEqual(result["hits"][0]["score"],3)
        self.assertEqual(result["passing_threshold_count"],1)

    def test_threshold_scale_and_empty_reason(self):
        service=SearchPipeline(self.corpus,method="dense",dense=FakeDense(),candidate_limit=3,top_k=2)
        with self.assertRaisesRegex(ValueError,"score scale"):
            service.search("тема",threshold={"score_type":"bm25","value":0.5})
        self.assertEqual(service.search("тема",threshold={"score_type":"cosine","value":1})["empty_reason"],"below_threshold")
        self.assertIsNone(service.search("тема")["threshold"])

    def test_invalid_queries_filters_and_limits(self):
        service=SearchPipeline(self.corpus,candidate_limit=3,top_k=2)
        for query in ("", "!!!", None):
            with self.assertRaises(ValueError): service.search(query)
        with self.assertRaises(ValueError): service.search("тема",filters={"typo":2026})
        with self.assertRaises(ValueError): service.search("тема",top_k=4)
        with self.assertRaises(ValueError): service.search("тема",exclude_ids="a")

    def test_hybrid_filters_apply_before_each_branch_cutoff(self):
        service=SearchPipeline(self.corpus,method="hybrid",dense=FakeDense(),candidate_limit=1,top_k=1,
                               rrf_config={"rrf_k":60,"candidate_depth":1,"weights":[1,1]})
        self.assertEqual(service.search("бета",filters={"year":2026})["hits"][0]["id"],"b")

    def test_bm25_empty_overlap_is_not_novelty_verdict(self):
        result=SearchPipeline(self.corpus,candidate_limit=3,top_k=2).search("несуществующий термин")
        self.assertEqual(result["status"],"empty")
        self.assertEqual(result["empty_reason"],"no_candidates")
        self.assertNotIn("is_duplicate",result)

    def test_annotations_are_opt_in_and_labels_not_indexed(self):
        records=[{"key":"x","name":"тема","abstract":"описание","duplicate_of":"SECRET"}]
        corpus=from_records(records,self.mapping)
        self.assertEqual(corpus.topics[0].text,"тема")
        config={**self.mapping,"annotation_field":"abstract","include_annotation":True}
        self.assertEqual(from_records(records,config).topics[0].text,"тема\n\nописание")

    def test_annotation_kept_for_display_with_origin(self):
        records=[{"key":"x","name":"тема","abstract":" описание ","source":"generated"},
                 {"key":"y","name":"вторая","abstract":"текст"},
                 {"key":"z","name":"третья","abstract":"  ","source":"original"}]
        config={**self.mapping,"annotation_field":"abstract","annotation_origin_field":"source"}
        x,y,z=from_records(records,config).topics
        self.assertEqual((x.text,x.annotation,x.annotation_origin),("тема","описание","generated"))
        self.assertEqual((y.annotation,y.annotation_origin),("текст","unknown"))
        self.assertEqual((z.annotation,z.annotation_origin),(None,"missing"))
        self.assertEqual(from_records(records,self.mapping).topics[0].annotation_origin,"missing")
        with self.assertRaisesRegex(ValueError,"origin"):
            from_records([{**records[0],"source":"invented"}],config)

    def test_bad_corpus_and_filters_rejected(self):
        for records in ([self.records[0],self.records[0]],[{"key":"x","name":None}],[]):
            with self.assertRaises(ValueError): from_records(records,self.mapping)
        with self.assertRaisesRegex(ValueError,"filter"):
            from_records(self.records,{**self.mapping,"record_filter":{"missing":["value"]}})

    def test_external_formats_and_numeric_ids(self):
        cache=ROOT / ".cache" / "tests"
        cache.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            folder=Path(directory)
            record={"key":7,"name":"Внешняя тема","date":2026}
            (folder/"data.json").write_text(json.dumps({"items":[record]}),encoding="utf-8")
            (folder/"data.jsonl").write_text(json.dumps(record)+"\n",encoding="utf-8")
            (folder/"data.csv").write_text("key;name;date\n7;Внешняя тема;2026\n",encoding="utf-8")
            for suffix in ("json","jsonl","csv"):
                config={**self.mapping,"path":f"data.{suffix}","delimiter":";"}
                if suffix=="json": config["records_key"]="items"
                corpus=load_corpus(config,folder)
                self.assertEqual(corpus.topics[0].id,"7")
                self.assertEqual(corpus.topics[0].title,"Внешняя тема")


if __name__ == "__main__":
    unittest.main()
