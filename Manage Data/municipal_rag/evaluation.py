from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_gold(path: Path, split: str | None = None) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pending = [item.get("id") for item in records if item.get("reviewStatus") != "APPROVED"]
    if pending:
        raise ValueError(f"Benchmark contains {len(pending)} non-approved cases; human review is required")
    return [item for item in records if split is None or item.get("split") == split]


def retrieval_metrics(cases: list[dict[str, Any]], runs: dict[str, dict[str, Any]]) -> dict[str, float]:
    recall_hits, reciprocal = 0, 0.0
    for case in cases:
        relevant = set(case.get("relevantDocumentIds") or [])
        retrieved = runs.get(case["id"], {}).get("retrievedDocumentIds", [])
        if relevant & set(retrieved[:20]):
            recall_hits += 1
        ranks = [index for index, value in enumerate(retrieved[:10], 1) if value in relevant]
        reciprocal += 1 / min(ranks) if ranks else 0
    denominator = max(1, len(cases))
    return {"recallAt20": recall_hits / denominator, "mrrAt10": reciprocal / denominator}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a human-approved municipal RAG gold set")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--split", choices=("tuning", "validation", "test"), default="test")
    args = parser.parse_args()
    try:
        cases = load_gold(args.gold, args.split)
        runs = {item["id"]: item for item in (json.loads(line) for line in args.runs.read_text(encoding="utf-8").splitlines() if line.strip())}
        print(json.dumps(retrieval_metrics(cases, runs), indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

