"""Simple interactive test for Romanian municipal-document search.

Examples:
    python test_romanian_search.py
    python test_romanian_search.py --question "Care este scopul evaluării?"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
SEARCH_SCRIPT = SCRIPT_DIRECTORY / "09_search_qdrant.py"
DEFAULT_COLLECTION = "municipal_documents"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Romanian semantic search.")
    parser.add_argument("--question", help="Romanian question. If omitted, you will be prompted.")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    return parser.parse_args()


def run_search(question: str, collection: str, limit: int) -> dict:
    command = [
        sys.executable,
        str(SEARCH_SCRIPT),
        "--text",
        question,
        "--limit",
        str(limit),
        "--collection",
        collection,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def print_results(response: dict) -> None:
    print(f"\nÎntrebare: {response['query']}")
    print(f"Rezultate găsite: {response['resultCount']}\n")
    for result in response["results"]:
        print(f"#{result['rank']} — scor {result['score']:.4f}")
        print(f"Document: {result.get('title') or result.get('documentId')}")
        print(f"Stare: {result.get('indexingStatus')}")
        citations = result.get("citations") or []
        if citations:
            print(f"Citări în fragment: {len(citations)}")
            for citation_number, citation in enumerate(citations, start=1):
                locator = citation.get("locator") or {}
                location = ""
                if locator.get("kind") == "source_lines":
                    location = f" (liniile {locator.get('startLine')}–{locator.get('endLine')})"
                print(f"  [{citation_number}]{location} {citation.get('quote', '').strip()}")
            if citations[0].get("sourceUrl"):
                print(f"Sursă: {citations[0]['sourceUrl']}")
        else:
            print("Pasaj: nicio citare disponibilă")
        print("-" * 72)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    arguments = parse_arguments()
    question = arguments.question or input("Scrie întrebarea în română: ").strip()
    if not question:
        print("Întrebarea nu poate fi goală.", file=sys.stderr)
        return 1
    try:
        response = run_search(question, arguments.collection, arguments.limit)
        print_results(response)
    except (json.JSONDecodeError, OSError, RuntimeError, ValueError) as error:
        print(f"Eroare: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
