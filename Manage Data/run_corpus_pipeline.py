"""Fault-isolated runner for the latest snapshot of every corpus document."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from batch_reporting import (
    DEFAULT_REVIEW_ROOT,
    atomic_replace_json,
    new_run_id,
    refresh_review_outputs,
    utc_now,
)
from pipeline_core import managed_relative, stable_id


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_INPUT_ROOT = SCRIPT_DIRECTORY / "Original Data" / "municipal_corpus"


def parse_api_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("updated_at is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("updated_at has no timezone")
    return parsed


def read_api_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid corpus snapshot {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Corpus snapshot is not an object: {path}")
    if not isinstance(value.get("id"), str) or not value["id"]:
        raise ValueError(f"Corpus snapshot has no id: {path}")
    parse_api_timestamp(value.get("updated_at"))
    return value


def first_source_url(document: dict[str, Any]) -> str | None:
    """Return the first usable source URL from a scraper snapshot."""
    urls = document.get("urls")
    if not isinstance(urls, list):
        return None
    for item in urls:
        value = item.get("url") if isinstance(item, dict) else item
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value
    return None


def scraper_title(document: dict[str, Any], fallback: str) -> str:
    title = document.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    urls = document.get("urls")
    if isinstance(urls, list):
        for item in urls:
            if not isinstance(item, dict):
                continue
            for key in ("title", "anchor_text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return fallback


def read_scraper_document(path: Path) -> dict[str, Any]:
    """Validate and adapt a chisinau-corpus extracted JSON record in memory."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid scraper snapshot {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Scraper snapshot is not an object: {path}")

    sha1 = value.get("sha1")
    if not isinstance(sha1, str) or len(sha1) != 40:
        raise ValueError(f"Scraper snapshot has no valid sha1: {path}")
    if path.stem.lower() != sha1.lower():
        raise ValueError(f"Scraper snapshot sha1 does not match its filename: {path}")
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"Scraper snapshot has no source: {path}")
    canonical_url = first_source_url(value)
    if canonical_url is None:
        raise ValueError(f"Scraper snapshot has no usable HTTP source URL: {path}")
    pages = value.get("pages")
    text = value.get("text")
    if pages is not None and not isinstance(pages, list):
        raise ValueError(f"Scraper snapshot pages must be an array: {path}")
    if text is not None and not isinstance(text, str):
        raise ValueError(f"Scraper snapshot text must be a string: {path}")
    if pages is None and text is None:
        raise ValueError(f"Scraper snapshot has neither pages nor text: {path}")
    quality_flags = value.get("quality_flags")
    if quality_flags is not None and not isinstance(quality_flags, list):
        raise ValueError(f"Scraper snapshot quality_flags must be an array: {path}")

    identity = value.get("act_id") or canonical_url
    adapted = dict(value)
    adapted.update({
        "id": stable_id("municipal", source, str(identity), length=24),
        "updated_at": value.get("extracted_at")
        or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "canonical_url": canonical_url,
        "extraction_method": value.get("method"),
        "ocr_pending_pages": value.get("needs_ocr_pages") or [],
        "title": scraper_title(value, f"Document {sha1[:12]}"),
        "_corpus_format": "chisinau_scraper_v1",
    })
    parse_api_timestamp(adapted["updated_at"])
    return adapted


def discovery_error(document_id: str, source: Path, messages: list[str]) -> dict[str, Any]:
    return {
        "documentId": document_id,
        "title": None,
        "sourceSnapshot": managed_relative(source),
        "status": "ERROR",
        "pipelineStatus": "DISCOVERY_ERROR",
        "indexingDecision": "BLOCKED",
        "chunks": None,
        "failedStage": {"number": 0, "name": "discovery", "retryable": True},
        "issues": [
            {
                "severity": "ERROR",
                "code": "INVALID_SNAPSHOT",
                "stage": 0,
                "message": message,
                "retryable": True,
            }
            for message in messages
        ],
        "artifacts": {},
    }


def discover_scraper_snapshot_records(root: Path) -> list[dict[str, Any]]:
    extraction_statuses: dict[str, str] = {}
    database = root / "manifest.sqlite"
    if database.is_file():
        try:
            connection = sqlite3.connect(
                f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True
            )
            try:
                extraction_statuses = {
                    str(sha1): str(status)
                    for sha1, status in connection.execute(
                        "SELECT sha1, status FROM extracted"
                    )
                    if sha1 and status
                }
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ValueError(f"Cannot read scraper extraction statuses: {error}") from error

    records: list[dict[str, Any]] = []
    for path in sorted((root / "text").glob("*/*.json")):
        try:
            document = read_scraper_document(path)
            document["_extraction_status"] = extraction_statuses.get(document["sha1"])
            records.append({"path": path, "document": document, "result": None})
        except (OSError, ValueError) as error:
            records.append({
                "path": None,
                "document": None,
                "result": discovery_error(path.stem, path, [str(error)]),
            })
    return records


def discover_snapshot_records(input_root: Path) -> list[dict[str, Any]]:
    root = input_root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Corpus directory does not exist: {root}")
    if (root / "text").is_dir():
        return discover_scraper_snapshot_records(root)
    records: list[dict[str, Any]] = []
    for document_directory in sorted(path for path in root.iterdir() if path.is_dir()):
        candidates: list[tuple[datetime, int, str, Path, dict[str, Any]]] = []
        errors: list[str] = []
        json_paths = sorted(document_directory.glob("*.json"))
        if not json_paths:
            errors.append(f"Document directory contains no JSON snapshots: {document_directory}")
        for path in json_paths:
            try:
                document = read_api_document(path)
                if document["id"] != document_directory.name:
                    raise ValueError(
                        f"Snapshot id {document['id']!r} does not match directory "
                        f"{document_directory.name!r}: {path}"
                    )
                candidates.append((
                    parse_api_timestamp(document["updated_at"]),
                    path.stat().st_mtime_ns,
                    path.name,
                    path,
                    document,
                ))
            except (OSError, ValueError) as error:
                errors.append(str(error))
        if errors:
            records.append({
                "path": None,
                "document": None,
                "result": discovery_error(document_directory.name, document_directory, errors),
            })
        elif candidates:
            _, _, _, path, document = max(candidates, key=lambda item: item[:3])
            records.append({"path": path, "document": document, "result": None})
    return records


def discover_latest_snapshots(input_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Compatibility helper used by existing callers and tests."""
    return [
        (record["path"], record["document"])
        for record in discover_snapshot_records(input_root)
        if record["result"] is None
    ]


def infer_document_type(document: dict[str, Any]) -> str:
    if isinstance(document.get("act"), dict) or document.get("category") == "legal_act":
        return "legal_act"
    content_type = document.get("content_type")
    if content_type == "text/html":
        return "webpage_article"
    if content_type == "application/pdf":
        return "administrative_document"
    return "municipal_document"


def optional_argument(flag: str, value: Any) -> list[str]:
    return [flag, str(value)] if value is not None and str(value).strip() else []


def run_snapshot(
    snapshot: Path, document: dict[str, Any], max_tokens: int, ready_only: bool
) -> dict[str, Any]:
    retrieved_at = document.get("updated_at") or datetime.fromtimestamp(
        snapshot.stat().st_mtime, timezone.utc
    ).isoformat()
    source_type = (
        "chisinau_scraper_snapshot"
        if document.get("_corpus_format") == "chisinau_scraper_v1"
        else "municipal_corpus_api"
    )
    command = [
        sys.executable,
        str(SCRIPT_DIRECTORY / "run_pipeline.py"),
        str(snapshot),
        "--document-id", document["id"],
        "--source-type", source_type,
        "--document-type", infer_document_type(document),
        "--language", document.get("lang") or "ro",
        "--retrieved-at", retrieved_at,
        "--max-tokens", str(max_tokens),
    ]
    for flag, value in (
        ("--title", document.get("title")),
        ("--source-url", document.get("canonical_url")),
        ("--publisher", document.get("source")),
        ("--published-date", document.get("doc_date")),
        ("--source-status", document.get("_extraction_status")),
    ):
        command.extend(optional_argument(flag, value))
    if ready_only:
        command.append("--ready-only")

    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    try:
        pipeline_result = json.loads(result.stdout)
    except json.JSONDecodeError:
        message = result.stderr.strip() or result.stdout.strip() or "Pipeline returned no JSON result."
        return {
            "documentId": document["id"],
            "title": document.get("title"),
            "sourceSnapshot": managed_relative(snapshot),
            "status": "ERROR",
            "pipelineStatus": "RUNNER_ERROR",
            "indexingDecision": "BLOCKED",
            "chunks": None,
            "failedStage": {"number": None, "name": "runner", "retryable": True},
            "issues": [{
                "severity": "ERROR",
                "code": "INVALID_PIPELINE_RESULT",
                "stage": None,
                "message": message,
                "retryable": True,
            }],
            "artifacts": {},
        }
    outcome = pipeline_result.get("outcome")
    if result.returncode or outcome not in {"READY", "WARNING", "ERROR"}:
        outcome = "ERROR"
        pipeline_result.setdefault("issues", []).append({
            "severity": "ERROR",
            "code": "PIPELINE_PROCESS_FAILED",
            "stage": None,
            "message": result.stderr.strip() or f"Pipeline exited with {result.returncode}.",
            "retryable": True,
        })
    return {
        "documentId": document["id"],
        "title": document.get("title"),
        "sourceSnapshot": managed_relative(snapshot),
        "status": outcome,
        "pipelineStatus": pipeline_result.get("pipelineStatus"),
        "indexingDecision": pipeline_result.get("indexingDecision"),
        "chunks": managed_relative(Path(pipeline_result["chunks"]))
        if isinstance(pipeline_result.get("chunks"), str) else None,
        "failedStage": pipeline_result.get("failedStage"),
        "issues": pipeline_result.get("issues") or [],
        "artifacts": pipeline_result.get("artifacts") or {},
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process corpus documents without batch-wide failure.")
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--max-tokens", type=int, default=420)
    parser.add_argument("--ready-only", action="store_true")
    parser.add_argument("--pipeline-workers", type=int, default=4)
    parser.add_argument("--run-id")
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()
    if arguments.max_documents is not None and arguments.max_documents < 1:
        parser.error("--max-documents must be at least 1")
    if arguments.max_tokens < 64:
        parser.error("--max-tokens must be at least 64")
    if not 1 <= arguments.pipeline_workers <= 32:
        parser.error("--pipeline-workers must be between 1 and 32")
    return arguments


def emit_progress(
    completed: int,
    total: int,
    counts: Counter[str],
    started: float,
    *,
    force: bool = False,
) -> None:
    if not force and completed % 100:
        return
    elapsed = max(time.monotonic() - started, 0.001)
    rate = completed / elapsed
    remaining = max(total - completed, 0)
    eta_seconds = int(remaining / rate) if rate else 0
    eta_minutes, eta_remainder = divmod(eta_seconds, 60)
    print(
        f"[documents] {completed:,}/{total:,} ({completed / max(total, 1):.1%}) | "
        f"ready={counts['READY']:,} warning={counts['WARNING']:,} "
        f"error={counts['ERROR']:,} | {rate:.1f} docs/s | "
        f"ETA {eta_minutes:d}m {eta_remainder:02d}s",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    run_id = arguments.run_id or new_run_id()
    started_at = utc_now()
    try:
        print(
            f"[documents] Discovering snapshots in {arguments.input_root}...",
            file=sys.stderr,
            flush=True,
        )
        records = discover_snapshot_records(arguments.input_root)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    full_run = arguments.max_documents is None
    if arguments.max_documents is not None:
        records = records[: arguments.max_documents]

    results = [record["result"] for record in records if record["result"] is not None]
    processable = [record for record in records if record["result"] is None]
    progress_started = time.monotonic()
    progress_counts: Counter[str] = Counter(
        str(result.get("status")) for result in results if isinstance(result, dict)
    )
    completed = len(results)
    print(
        f"[documents] Discovered {len(records):,}; processing with "
        f"{arguments.pipeline_workers} workers.",
        file=sys.stderr,
        flush=True,
    )
    if completed:
        emit_progress(completed, len(records), progress_counts, progress_started, force=True)
    with ThreadPoolExecutor(max_workers=arguments.pipeline_workers) as executor:
        futures = {
            executor.submit(
                run_snapshot,
                record["path"],
                record["document"],
                arguments.max_tokens,
                arguments.ready_only,
            ): record["document"]["id"]
            for record in processable
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as error:
                document_id = futures[future]
                result = discovery_error(
                    document_id, arguments.input_root / document_id, [str(error)]
                )
            results.append(result)
            completed += 1
            progress_counts[str(result.get("status"))] += 1
            emit_progress(completed, len(records), progress_counts, progress_started)

    emit_progress(completed, len(records), progress_counts, progress_started, force=True)

    results.sort(key=lambda item: str(item.get("documentId", "")))
    review_directory = arguments.review_root.expanduser().resolve() / run_id
    manifest_path = review_directory / "run-manifest.json"
    manifest = {
        "schemaVersion": 1,
        "runId": run_id,
        "scope": "FULL" if full_run else "PARTIAL",
        "startedAt": started_at,
        "completedAt": utc_now(),
        "inputRoot": managed_relative(arguments.input_root),
        "documents": results,
        "database": None,
    }
    atomic_replace_json(manifest_path, manifest)
    summary = refresh_review_outputs(manifest_path)
    output = {
        "runId": run_id,
        "status": summary["status"],
        "scope": manifest["scope"],
        "counts": summary["counts"],
        "runManifest": str(manifest_path),
        "reviewDirectory": str(review_directory),
    }
    if arguments.verbose:
        output["results"] = results
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
