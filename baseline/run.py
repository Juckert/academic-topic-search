"""Run retrieval against a user-supplied local corpus."""
import argparse
from baseline.io import ROOT, read_json
from baseline.search import BM25
from topic_search.corpus import load_corpus

METHODS = ("bm25",)

def build(method, corpus_config="configs/corpus-example.json"):
    corpus = load_corpus(read_json(ROOT / corpus_config), ROOT)
    documents = [(d.id, d.text) for d in corpus.topics]
    bm25 = read_json(ROOT / "configs/bm25.json")
    if method == "bm25":
        return BM25(documents, **bm25)
    raise ValueError("Unsupported method in this branch")

def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, default=METHODS[-1])
    parser.add_argument("--corpus-config", default="configs/corpus-example.json")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("top-k must be positive")
    print(json.dumps(build(args.method, args.corpus_config).search(args.query, args.top_k), ensure_ascii=False))

if __name__ == "__main__":
    main()
