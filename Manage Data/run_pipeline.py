"""Run data-preparation steps 1 through 6 as one reproducible command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from batch_reporting import artifact_paths
from pipeline_core import read_json


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


STAGE_NAMES = {
    1: "ingest",
    2: "extract",
    3: "structure",
    4: "enrich",
    5: "validate",
    6: "chunk",
}


def validation_issues(validated_path: str) -> list[dict[str, Any]]:
    document = read_json(Path(validated_path))
    codes: list[str] = []
    validation = document.get("validation", {})
    for key in ("dataIssues", "citationIssues"):
        values = validation.get(key, [])
        if isinstance(values, list):
            codes.extend(str(value) for value in values)
    for passage in document.get("passages", []):
        passage_validation = passage.get("validation", {})
        for key in ("dataIssues", "citationIssues"):
            values = passage_validation.get(key, [])
            if isinstance(values, list):
                codes.extend(str(value) for value in values)
    unique_codes = list(dict.fromkeys(codes))
    return [
        {
            "severity": "WARNING",
            "code": code,
            "stage": 5,
            "message": code,
            "retryable": True,
        }
        for code in unique_codes
    ]


def emit_result(
    document_id: str | None,
    outcome: str,
    pipeline_status: str,
    indexing_decision: str,
    stages: list[dict[str, Any]],
    chunks: str | None = None,
    issues: list[dict[str, Any]] | None = None,
    failed_stage: dict[str, Any] | None = None,
) -> int:
    print(json.dumps({
        "documentId": document_id,
        "outcome": outcome,
        "pipelineStatus": pipeline_status,
        "indexingDecision": indexing_decision,
        "chunks": chunks,
        "issues": issues or [],
        "failedStage": failed_stage,
        "artifacts": artifact_paths(stages),
        "stages": stages,
    }, ensure_ascii=False, indent=2))
    return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run municipal data preparation steps 1-6.")
    parser.add_argument("input", type=Path, help="Original TXT, HTML, PDF, or corpus API JSON artifact.")
    parser.add_argument("--title")
    parser.add_argument("--document-id")
    parser.add_argument("--source-url")
    parser.add_argument("--source-type")
    parser.add_argument("--document-type")
    parser.add_argument("--publisher")
    parser.add_argument("--published-date")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--source-status")
    parser.add_argument("--language", default="ro")
    parser.add_argument("--max-tokens", type=int, default=420)
    parser.add_argument(
        "--ready-only",
        action="store_true",
        help="Write only production-ready chunks. Review documents may produce zero chunks.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    ingest_arguments = [str(arguments.input), "--language", arguments.language]
    for flag, value in (
        ("--title", arguments.title),
        ("--document-id", arguments.document_id),
        ("--source-url", arguments.source_url),
        ("--source-type", arguments.source_type),
        ("--document-type", arguments.document_type),
        ("--publisher", arguments.publisher),
        ("--published-date", arguments.published_date),
        ("--retrieved-at", arguments.retrieved_at),
        ("--source-status", getattr(arguments, "source_status", None)),
    ):
        ingest_arguments.extend(optional_argument(flag, value))

    stages: list[dict[str, Any]] = []
    current_stage = 1
    document_id = arguments.document_id
    try:
        stage_1 = run_stage("01_ingest_source.py", ingest_arguments)
        stages.append({"stage": 1, **stage_1})
        document_id = stage_1["documentId"]
        current_stage = 2
        extraction_arguments = [stage_1["manifest"]]
        extraction_arguments.extend(
            optional_argument("--source-status", getattr(arguments, "source_status", None))
        )
        stage_2 = run_stage("02_extract_content.py", extraction_arguments)
        stages.append({"stage": 2, **stage_2})
        if stage_2["extractionStatus"] != "READY":
            status = str(stage_2["extractionStatus"])
            return emit_result(
                document_id,
                "WARNING",
                status,
                "BLOCKED",
                stages,
                issues=[{
                    "severity": "WARNING",
                    "code": f"EXTRACTION_{status}",
                    "stage": 2,
                    "message": f"Extraction requires review: {status}",
                    "retryable": True,
                }],
                failed_stage={"number": 2, "name": STAGE_NAMES[2], "retryable": True},
            )
        current_stage = 3
        stage_3 = run_stage("03_structure_document.py", [stage_2["output"]])
        stages.append({"stage": 3, **stage_3})
        current_stage = 4
        stage_4 = run_stage("04_enrich_document.py", [stage_3["output"]])
        stages.append({"stage": 4, **stage_4})
        current_stage = 5
        stage_5 = run_stage("05_validate_document.py", [stage_4["output"]])
        stages.append({"stage": 5, **stage_5})
        validation = stage_5["validation"]
        if validation.get("indexingDecision") != "PRODUCTION":
            return emit_result(
                document_id,
                "WARNING",
                str(validation.get("overallStatus") or "NEEDS_REVIEW"),
                str(validation.get("indexingDecision") or "REVIEW"),
                stages,
                issues=validation_issues(stage_5["output"]),
                failed_stage={"number": 5, "name": STAGE_NAMES[5], "retryable": True},
            )
        current_stage = 6
        chunk_arguments = [stage_5["output"], "--max-tokens", str(arguments.max_tokens)]
        if arguments.ready_only:
            chunk_arguments.append("--ready-only")
        stage_6 = run_stage("06_create_chunks.py", chunk_arguments)
        stages.append({"stage": 6, **stage_6})
        if int(stage_6.get("chunkCount") or 0) == 0:
            return emit_result(
                document_id,
                "WARNING",
                "ALL_PASSAGES_QUARANTINED",
                "REVIEW",
                stages,
                issues=validation_issues(stage_5["output"]) + [{
                    "severity": "WARNING",
                    "code": "ALL_PASSAGES_QUARANTINED",
                    "stage": 6,
                    "message": "No passage passed v3 production quality filters.",
                    "retryable": True,
                }],
                failed_stage={"number": 6, "name": STAGE_NAMES[6], "retryable": True},
            )
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        return emit_result(
            document_id,
            "ERROR",
            "ERROR",
            "BLOCKED",
            stages,
            issues=[{
                "severity": "ERROR",
                "code": "STAGE_FAILED",
                "stage": current_stage,
                "message": str(error),
                "retryable": current_stage >= 2,
            }],
            failed_stage={
                "number": current_stage,
                "name": STAGE_NAMES[current_stage],
                "retryable": current_stage >= 2,
            },
        )

    return emit_result(
        document_id,
        "READY",
        stage_5["validation"]["overallStatus"],
        stage_5["validation"]["indexingDecision"],
        stages,
        issues=validation_issues(stage_5["output"]),
        chunks=stage_6["output"],
    )


if __name__ == "__main__":
    raise SystemExit(main())
