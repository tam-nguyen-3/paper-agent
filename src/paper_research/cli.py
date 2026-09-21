"""Command-line interface for the arXiv search client."""

import argparse
import json

from .providers.arxiv import search


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the arXiv API")
    parser.add_argument("query", help='arXiv query, e.g. all:"self improving agents"')
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument(
        "--sort-by",
        choices=("relevance", "lastUpdatedDate", "submittedDate"),
        default="relevance",
    )
    parser.add_argument(
        "--sort-order", choices=("ascending", "descending"), default="descending"
    )
    args = parser.parse_args()

    result = search(
        args.query,
        max_results=args.max_results,
        start=args.start,
        sort_by=args.sort_by,
        sort_order=args.sort_order,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
