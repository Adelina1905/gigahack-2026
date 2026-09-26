"""Run data-preparation steps 1 through 6 as one reproducible command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIRECTORY = Path(__file__).resolve().parent


def run_stage(script: str, arguments: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(SCRIPT_DIRECTORY / script), *arguments]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"{script} failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{script} returned invalid JSON: {result.stdout.strip()}") from error


def optional_argument(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run municipal data preparation steps 1-6.")
    parser.add_argument("input", type=Path, help="Original TXT, HTML, or PDF source artifact.")
    parser.add_argument("--title")
    parser.add_argument("--source-url")
    parser.add_argument("--source-type")
    parser.add_argument("--document-type")
    parser.add_argument("--publisher")
    parser.add_argument("--published-date")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--language", default="ro")
    parser.add_argument("--max-tokens", type=int, default=450)
    parser.add_argument(
        "--ready-only",
        action="store_true",
        help="Write only production-ready chunks. Review documents may produce zero chunks.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    ingest_arguments = [str(arguments.input), "--language", arguments.language]
    for flag, value in (
        ("--title", arguments.title),
        ("--source-url", arguments.source_url),
        ("--source-type", arguments.source_type),
        ("--document-type", arguments.document_type),
        ("--publisher", arguments.publisher),
        ("--published-date", arguments.published_date),
        ("--retrieved-at", arguments.retrieved_at),
    ):
        ingest_arguments.extend(optional_argument(flag, value))

    try:
        stages: list[dict[str, Any]] = []
        stage_1 = run_stage("01_ingest_source.py", ingest_arguments)
        stages.append({"stage": 1, **stage_1})
        stage_2 = run_stage("02_extract_content.py", [stage_1["manifest"]])
        stages.append({"stage": 2, **stage_2})
        if stage_2["extractionStatus"] != "READY":
            print(json.dumps({
                "documentId": stage_1["documentId"],
                "pipelineStatus": stage_2["extractionStatus"],
                "indexingDecision": "BLOCKED",
                "chunks": None,
                "stages": stages,
            }, ensure_ascii=False, indent=2))
            return 0
        stage_3 = run_stage("03_structure_document.py", [stage_2["output"]])
        stages.append({"stage": 3, **stage_3})
        stage_4 = run_stage("04_enrich_document.py", [stage_3["output"]])
        stages.append({"stage": 4, **stage_4})
        stage_5 = run_stage("05_validate_document.py", [stage_4["output"]])
        stages.append({"stage": 5, **stage_5})
        chunk_arguments = [stage_5["output"], "--max-tokens", str(arguments.max_tokens)]
        if arguments.ready_only:
            chunk_arguments.append("--ready-only")
        stage_6 = run_stage("06_create_chunks.py", chunk_arguments)
        stages.append({"stage": 6, **stage_6})
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    result = {
        "documentId": stage_1["documentId"],
        "pipelineStatus": stage_5["validation"]["overallStatus"],
        "indexingDecision": stage_5["validation"]["indexingDecision"],
        "chunks": stage_6["output"],
        "stages": stages,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
