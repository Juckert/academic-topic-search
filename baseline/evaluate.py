"""Evaluate an externally supplied query set with one known relevant ID per query."""
import argparse
import json
from baseline.io import ROOT, read_json, dump
from baseline.metrics import metrics
from baseline.run import METHODS, build
from topic_search.corpus import load_corpus

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, default=METHODS[-1])
    parser.add_argument("--corpus-config", default="configs/corpus-example.json")
    parser.add_argument("--queries", required=True)
    parser.add_argument("--cutoffs", type=int, nargs="+", default=[1,5,10])
    parser.add_argument("--output", help="Optional local JSON output; results/ is ignored by Git")
    args = parser.parse_args()
    if not args.cutoffs or min(args.cutoffs) < 1:
        parser.error("cutoffs must be positive")
    queries = read_json(ROOT / args.queries)
    corpus = load_corpus(read_json(ROOT / args.corpus_config), ROOT)
    ids = {d.id for d in corpus.topics}
    if not queries or len({q["query_id"] for q in queries}) != len(queries):
        raise ValueError("Nonempty queries with unique query_id required")
    if any(q["expected_match_id"] not in ids or not isinstance(q["query"],str) or not q["query"].strip() for q in queries):
        raise ValueError("Each query needs nonempty text and an expected_match_id present in the corpus")
    index = build(args.method, args.corpus_config)
    ranks = []
    for query in queries:
        hits = index.search(query["query"], max(args.cutoffs))
        ranks.append(next((rank for rank,(doc_id,_) in enumerate(hits,1) if doc_id == query["expected_match_id"]),None))
    result = {"method":args.method,"queries":len(queries),"metrics":metrics(ranks,args.cutoffs),
              "scope":"One known relevant document per query; not duplicate classification or threshold calibration"}
    if args.output:
        path = ROOT / args.output
        path.parent.mkdir(parents=True,exist_ok=True)
        dump(path,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
