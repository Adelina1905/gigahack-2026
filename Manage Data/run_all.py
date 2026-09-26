"""Run corpus preparation and AI database indexing as one command."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from batch_reporting import DEFAULT_REVIEW_ROOT, new_run_id, read_manifest, refresh_review_outputs


SCRIPT_DIRECTORY = Path(__file__).resolve().parent


def run_json_command(command: list[str], label: str) -> dict[str, Any]:
    print(f"[{label}] Starting...", file=sys.stderr, flush=True)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    stderr_parts: list[str] = []

    def relay_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_parts.append(line)
            sys.stderr.write(line)
            sys.stderr.flush()

    relay = threading.Thread(target=relay_stderr, daemon=True)
    relay.start()
    assert process.stdout is not None
    stdout = process.stdout.read()
    return_code = process.wait()
    relay.join()
    if return_code:
        detail = "".join(stderr_parts).strip() or stdout.strip() or "unknown error"
        raise RuntimeError(f"{label} failed: {detail}")
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} returned invalid JSON: {stdout.strip()}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} returned a non-object JSON result")
    return value


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optionally collect documents, process them, and update the AI database."
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Collect new API documents before running the local pipeline.",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        help="Read an existing corpus root instead of the default Original Data/municipal_corpus.",
    )
    parser.add_argument(
        "--collect-max-documents",
        type=int,
        help="Stop API collection after N documents (useful for a test).",
    )
    parser.add_argument("--collect-page-size", type=int, default=100)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Generate real OpenRouter embeddings and update production Qdrant.",
    )
    mode.add_argument(
        "--mock",
        action="store_true",
        help="Use isolated test vectors without calling OpenRouter.",
    )
    parser.add_argument("--max-documents", type=int, help="Process only the first N snapshots.")
    parser.add_argument("--max-tokens", type=int, default=420)
    parser.add_argument("--ready-only", action="store_true")
    parser.add_argument("--pipeline-workers", type=int, default=4)
    parser.add_argument("--embedding-workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--model", default="qwen/qwen3-embedding-8b")
    parser.add_argument("--collection", default="municipal_evidence_current")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--qdrant-url")
    location.add_argument("--qdrant-path", type=Path)
    arguments = parser.parse_args()
    if arguments.max_documents is not None and arguments.max_documents < 1:
        parser.error("--max-documents must be at least 1")
    if arguments.collect_max_documents is not None and arguments.collect_max_documents < 1:
        parser.error("--collect-max-documents must be at least 1")
    if not 1 <= arguments.collect_page_size <= 500:
        parser.error("--collect-page-size must be between 1 and 500")
    if arguments.max_tokens < 64:
        parser.error("--max-tokens must be at least 64")
    if not 1 <= arguments.pipeline_workers <= 32:
        parser.error("--pipeline-workers must be between 1 and 32")
    if not 1 <= arguments.embedding_workers <= 16:
        parser.error("--embedding-workers must be between 1 and 16")
    if not 0 <= arguments.retries <= 10:
        parser.error("--retries must be between 0 and 10")
    return arguments


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    run_id = new_run_id()
    predicted_review_directory = arguments.review_root.expanduser().resolve() / run_id

    collection_command = [
        sys.executable,
        str(SCRIPT_DIRECTORY / "fetch_municipal_corpus.py"),
        "--page-size",
        str(arguments.collect_page_size),
    ]
    if arguments.collect_max_documents is not None:
        collection_command.extend(
            ["--max-documents", str(arguments.collect_max_documents)]
        )

    pipeline_command = [
        sys.executable,
        str(SCRIPT_DIRECTORY / "run_corpus_pipeline.py"),
        "--max-tokens",
        str(arguments.max_tokens),
        "--pipeline-workers",
        str(arguments.pipeline_workers),
        "--run-id",
        run_id,
        "--review-root",
        str(arguments.review_root),
    ]
    if arguments.input_root is not None:
        pipeline_command.extend(["--input-root", str(arguments.input_root)])
    if arguments.max_documents is not None:
        pipeline_command.extend(["--max-documents", str(arguments.max_documents)])
    if arguments.ready_only:
        pipeline_command.append("--ready-only")
    if arguments.verbose:
        pipeline_command.append("--verbose")

    try:
        collection = (
            run_json_command(collection_command, "API collection")
            if arguments.collect
            else None
        )
        pipeline = run_json_command(pipeline_command, "document pipeline")
        database_command = [
            sys.executable,
            str(SCRIPT_DIRECTORY / "prepare_ai_database.py"),
            "--run-manifest",
            pipeline["runManifest"],
            "--model",
            arguments.model,
            "--collection",
            arguments.collection,
            "--embedding-workers",
            str(arguments.embedding_workers),
            "--retries",
            str(arguments.retries),
        ]
        if arguments.execute:
            database_command.append("--execute")
        elif arguments.mock:
            database_command.append("--mock")
        if arguments.qdrant_url:
            database_command.extend(["--qdrant-url", arguments.qdrant_url])
        elif arguments.qdrant_path:
            database_command.extend(["--qdrant-path", str(arguments.qdrant_path)])
        if arguments.verbose:
            database_command.append("--verbose")
        database = run_json_command(database_command, "AI database preparation")
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        failed_manifest = predicted_review_directory / "run-manifest.json"
        print(json.dumps({
            "runId": run_id,
            "status": "FAILED",
            "documents": None,
            "database": {
                "expectedPoints": None,
                "actualPoints": None,
                "missingPoints": None,
                "stalePointsRemoved": None,
                "consistent": False,
            },
            "reviewDirectory": str(predicted_review_directory)
            if predicted_review_directory.exists() else None,
            "runManifest": str(failed_manifest) if failed_manifest.is_file() else None,
            "readyForQuestions": False,
            "error": str(error),
        }, ensure_ascii=False, indent=2))
        return 1

    manifest_path = Path(pipeline["runManifest"]).resolve()
    summary = refresh_review_outputs(manifest_path)
    manifest = read_manifest(manifest_path)
    ready_for_questions = bool(
        arguments.execute
        and database.get("consistent") is True
        and int(database.get("importedDocuments") or 0) > 0
    )
    output = {
        "runId": run_id,
        "status": summary["status"],
        "mode": "execute" if arguments.execute else ("mock" if arguments.mock else "dry-run"),
        "collection": ({
            "status": collection.get("status"),
            "documentsSeen": collection.get("documentsSeen"),
            "snapshotsCreated": collection.get("snapshotsCreated"),
        } if collection is not None else {"status": "skipped"}),
        "documents": manifest.get("counts"),
        "database": {
            "collection": database.get("collection"),
            "eligibleDocuments": database.get("eligibleDocuments"),
            "embeddedDocuments": database.get("embeddedDocuments"),
            "generatedEmbeddingDocuments": database.get("generatedEmbeddingDocuments"),
            "reusedEmbeddingDocuments": database.get("reusedEmbeddingDocuments"),
            "importedDocuments": database.get("importedDocuments"),
            "failedDocuments": database.get("failedDocuments"),
            "importedPoints": database.get("importedPoints"),
            "expectedPoints": database.get("expectedPoints"),
            "actualPoints": database.get("actualPoints"),
            "missingPoints": database.get("missingPoints"),
            "stalePointsRemoved": database.get("stalePointsRemoved"),
            "consistent": database.get("consistent"),
        },
        "reviewDirectory": pipeline.get("reviewDirectory"),
        "runManifest": pipeline.get("runManifest"),
        "readyForQuestions": ready_for_questions,
    }
    if arguments.verbose:
        output["details"] = {"pipeline": pipeline, "database": database}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
