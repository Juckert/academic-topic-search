"""CLI to search once or reuse a loaded pipeline interactively."""

import argparse
import json
import sys
from pathlib import Path

from topic_search import SearchPipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",default="configs/search.json")
    parser.add_argument("--device",help="Model device override: cpu, auto, cuda or cuda:<index>")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--query")
    mode.add_argument("--interactive",action="store_true")
    parser.add_argument("--top-k",type=int)
    parser.add_argument("--filters",default="{}",help="JSON object; values match metadata types exactly")
    parser.add_argument("--exclude-id",action="append",default=[])
    parser.add_argument("--threshold",help='JSON object with score_type and value')
    parser.add_argument("--output",help="Save one-query JSON response instead of printing")
    args = parser.parse_args()
    if args.interactive and args.output:
        parser.error("--output is only supported with --query")
    try:
        filters = json.loads(args.filters)
        threshold = json.loads(args.threshold) if args.threshold else None
        pipeline = SearchPipeline.from_config(args.config,device=args.device)
        def run(query):
            result = pipeline.search(query,top_k=args.top_k,filters=filters,exclude_ids=args.exclude_id,threshold=threshold)
            result["runtime"] = pipeline.runtime_info()
            return json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.interactive:
            print("Введите тему; пустая строка завершает поиск.",file=sys.stderr)
            for line in sys.stdin:
                if not line.strip():
                    break
                try:
                    print(run(line))
                except ValueError as exc:
                    print(str(exc),file=sys.stderr)
        else:
            result = run(args.query)
            if args.output:
                path = Path(args.output)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(result+"\n",encoding="utf-8")
            else:
                print(result)
    except (ValueError,KeyError,OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
