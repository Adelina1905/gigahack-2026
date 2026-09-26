"""Generate embeddings for all prepared chunks and import them into Qdrant."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from batch_reporting import atomic_replace_json, read_manifest, refresh_review_outputs, utc_now
from pipeline_core import managed_relative, resolve_managed_path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_CHUNKS_DIRECTORY = SCRIPT_DIRECTORY / "data" / "06_chunks"
DEFAULT_EMBEDDINGS_DIRECTORY = SCRIPT_DIRECTORY / "data" / "07_embeddings"
DEFAULT_QDRANT_PATH = SCRIPT_DIRECTORY / "data" / "08_qdrant"
DEFAULT_COLLECTION = "municipal_evidence_current"
DEFAULT_MODEL = "qwen/qwen3-embedding-8b"
STATE_FILENAME = ".batch-state.json"


def load_local_env(path: Path) -> None:
    """Load non-overriding KEY=VALUE entries for direct script execution."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": 1, "embeddings": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read batch state {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise RuntimeError(f"Unsupported batch state: {path}")
    if not isinstance(value.get("embeddings"), dict):
        raise RuntimeError(f"Invalid embeddings map in batch state: {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run_json_command(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Command returned invalid JSON: {result.stdout.strip()}") from error
    if not isinstance(value, dict):
        raise RuntimeError("Command returned a non-object JSON result")
    return value


def read_api_key(variable_name: str) -> str:
    value = os.environ.get(variable_name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment_key:
            stored, _ = winreg.QueryValueEx(environment_key, variable_name)
        return stored.strip() if isinstance(stored, str) else ""
    except (FileNotFoundError, OSError):
        return ""


def embedding_cache_key(chunk_path: Path, model: str, mock: bool) -> str:
    mode = "mock" if mock else "real"
    return f"{sha256_file(chunk_path)}:{model}:{mode}"


def read_jsonl_signature(path: Path) -> tuple[tuple[str, str], ...]:
    signature: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            item = json.loads(line)
            chunk_id = item.get("chunkId")
            text_hash = item.get("textSha256")
            if not isinstance(chunk_id, str):
                raise ValueError(f"Missing chunkId in {path}")
            if not isinstance(text_hash, str):
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError(f"Missing text/textSha256 in {path}")
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            signature.append((chunk_id, text_hash))
    return tuple(signature)


def discover_latest_chunk_files(directory: Path) -> list[Path]:
    """Keep only the newest immutable chunk version for each document."""
    latest: dict[str, Path] = {}
    for path in directory.glob("*.jsonl"):
        with path.open("r", encoding="utf-8") as source:
            first = next((json.loads(line) for line in source if line.strip()), None)
        if not isinstance(first, dict) or not isinstance(first.get("documentId"), str):
            raise ValueError(f"Cannot determine documentId from {path}")
        document_id = first["documentId"]
        current = latest.get(document_id)
        if current is None or path.stat().st_mtime_ns > current.stat().st_mtime_ns:
            latest[document_id] = path
    return sorted(latest.values())


def find_compatible_embeddings(
    chunk_path: Path,
    embeddings_directory: Path,
    model: str,
    mock: bool,
) -> Path | None:
    """Reuse vectors when only citation metadata changed, not searchable text."""
    expected_signature = read_jsonl_signature(chunk_path)
    requested_model = model.lower()
    for candidate in sorted(embeddings_directory.glob("*.jsonl")):
        first_record: dict[str, Any] | None = None
        candidate_signature: list[tuple[str, str]] = []
        try:
            with candidate.open("r", encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if first_record is None:
                        first_record = record
                    candidate_signature.append((record["chunkId"], record["textSha256"]))
        except (OSError, KeyError, json.JSONDecodeError, TypeError):
            continue
        if first_record is None or tuple(candidate_signature) != expected_signature:
            continue
        stored_model = str(first_record.get("model", "")).lower()
        is_mock_file = stored_model.startswith("mock/")
        if is_mock_file == mock and (mock or stored_model == requested_model):
            return candidate.resolve()
    return None


def generate_embeddings(
    chunk_path: Path,
    output_directory: Path,
    model: str,
    execute: bool,
    mock: bool,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIRECTORY / "07_generate_embeddings.py"),
        str(chunk_path),
        "--model",
        model,
        "--output-dir",
        str(output_directory),
    ]
    if execute:
        command.append("--execute")
    elif mock:
        command.append("--mock")
    return run_json_command(command)


def import_embeddings(
    chunk_path: Path,
    embedding_path: Path,
    collection: str,
    qdrant_path: Path | None,
    qdrant_url: str | None,
    qdrant_api_key_env: str,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIRECTORY / "08_import_to_qdrant.py"),
        "--chunks",
        str(chunk_path),
        "--embeddings",
        str(embedding_path),
        "--collection",
        collection,
        "--qdrant-api-key-env",
        qdrant_api_key_env,
    ]
    if qdrant_url:
        command.extend(["--url", qdrant_url])
    else:
        command.extend(["--path", str((qdrant_path or DEFAULT_QDRANT_PATH).resolve())])
    return run_json_command(command)


def run_with_retry(operation: Any, retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries + 1):
        try:
            return operation()
        except RuntimeError as error:
            message = str(error).lower()
            retryable = any(marker in message for marker in (
                "http 429", "http 500", "http 502", "http 503", "http 504",
                "timed out", "timeout", "could not reach", "connection",
            ))
            if not retryable or attempt == retries:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Retry loop ended unexpectedly.")


def is_global_qdrant_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        "named-vector collections",
        " is incompatible",
        "connection refused",
        "actively refused",
        "could not reach",
        "service unavailable",
        "internal server error",
        "timed out",
        "unauthorized",
        "forbidden",
        "http 401",
        "http 403",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    ))


def chunk_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-chunk:{chunk_id}"))


def chunk_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict) or not isinstance(value.get("chunkId"), str):
                    raise ValueError(f"Invalid chunk record in {path}")
                records.append(value)
    if not records:
        raise ValueError(f"Chunk file contains no records: {path}")
    return records


def qdrant_client_for(
    qdrant_path: Path | None,
    qdrant_url: str | None,
    qdrant_api_key_env: str,
):
    from qdrant_client import QdrantClient

    if qdrant_url:
        api_key = read_api_key(qdrant_api_key_env) or None
        return QdrantClient(url=qdrant_url, api_key=api_key, timeout=20)
    local_path = (qdrant_path or DEFAULT_QDRANT_PATH).expanduser().resolve()
    local_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(local_path))


def reconcile_collection(
    documents: list[dict[str, Any]],
    scope: str,
    collection: str,
    qdrant_path: Path | None,
    qdrant_url: str | None,
    qdrant_api_key_env: str,
) -> dict[str, Any]:
    from qdrant_client import models

    expected_ids: set[str] = set()
    selected_document_ids = {str(document.get("documentId")) for document in documents}
    for document in documents:
        if document.get("status") != "READY" or document.get("databaseStatus") != "IMPORTED":
            continue
        chunks_value = document.get("chunks")
        if not isinstance(chunks_value, str):
            continue
        for chunk in chunk_records(resolve_managed_path(chunks_value)):
            expected_ids.add(chunk_point_id(chunk["chunkId"]))

    client = qdrant_client_for(qdrant_path, qdrant_url, qdrant_api_key_env)
    try:
        if not client.collection_exists(collection):
            if expected_ids:
                raise RuntimeError(f"Expected imported points but collection {collection!r} does not exist.")
            return {
                "expectedPoints": 0, "actualPoints": 0, "missingPoints": 0,
                "stalePointsRemoved": 0, "consistent": True,
            }
        actual_ids: set[str] = set()
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                if scope == "FULL" or str(payload.get("documentId")) in selected_document_ids:
                    actual_ids.add(str(record.id))
            if offset is None:
                break
        stale_ids = actual_ids - expected_ids
        if stale_ids:
            client.delete(
                collection_name=collection,
                points_selector=models.PointIdsList(points=sorted(stale_ids)),
                wait=True,
            )
        actual_after = actual_ids - stale_ids
        missing = expected_ids - actual_after
        return {
            "expectedPoints": len(expected_ids),
            "actualPoints": len(actual_after),
            "missingPoints": len(missing),
            "stalePointsRemoved": len(stale_ids),
            "consistent": not missing,
        }
    finally:
        client.close()


def add_document_failure(
    document: dict[str, Any], stage: int, name: str, code: str, message: str
) -> None:
    document["status"] = "ERROR"
    if stage <= 6:
        document["indexingDecision"] = "BLOCKED"
    document["failedStage"] = {"number": stage, "name": name, "retryable": True}
    document.setdefault("issues", []).append({
        "severity": "ERROR",
        "code": code,
        "stage": stage,
        "message": message,
        "retryable": True,
    })


def persist_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest["completedAt"] = utc_now()
    atomic_replace_json(manifest_path, manifest)
    refresh_review_outputs(manifest_path)


def restore_retryable_database_documents(documents: list[dict[str, Any]]) -> None:
    """Allow a repaired stage 7/8 run to reuse the same authoritative manifest."""
    for document in documents:
        failed_stage = document.get("failedStage") or {}
        if (
            document.get("status") != "ERROR"
            or failed_stage.get("number") not in {7, 8}
            or document.get("pipelineStatus") != "READY"
            or document.get("indexingDecision") != "PRODUCTION"
            or not isinstance(document.get("chunks"), str)
        ):
            continue
        previous_issues = [
            issue for issue in document.get("issues", [])
            if issue.get("stage") in {7, 8}
        ]
        document.setdefault("attemptHistory", []).append({
            "failedStage": failed_stage,
            "issues": previous_issues,
            "retriedAt": utc_now(),
        })
        document["issues"] = [
            issue for issue in document.get("issues", [])
            if issue.get("stage") not in {7, 8}
        ]
        document["status"] = "READY"
        document["failedStage"] = None
        document.pop("embeddingStatus", None)
        document.pop("databaseStatus", None)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed and import READY documents from an authoritative run manifest."
    )
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--chunks-dir", type=Path, default=DEFAULT_CHUNKS_DIRECTORY)
    parser.add_argument("--embeddings-dir", type=Path, default=DEFAULT_EMBEDDINGS_DIRECTORY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--qdrant-api-key-env", default="QDRANT_API_KEY")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Call OpenRouter and import real vectors.")
    mode.add_argument("--mock", action="store_true", help="Create test-only vectors and import them.")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--qdrant-url")
    location.add_argument("--qdrant-path", type=Path)
    parser.add_argument("--embedding-workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.embedding_workers <= 16:
        parser.error("--embedding-workers must be between 1 and 16")
    if not 0 <= arguments.retries <= 10:
        parser.error("--retries must be between 0 and 10")
    return arguments


def emit_phase_progress(
    phase: str,
    completed: int,
    total: int,
    started: float,
    *,
    force: bool = False,
) -> None:
    if not force and completed % 10:
        return
    elapsed = max(time.monotonic() - started, 0.001)
    rate = completed / elapsed
    remaining = max(total - completed, 0)
    eta = int(remaining / rate) if rate else 0
    hours, remainder = divmod(eta, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(
        f"[{phase}] {completed:,}/{total:,} ({completed / max(total, 1):.1%}) | "
        f"{rate:.2f} docs/s | ETA {hours:d}h {minutes:02d}m {seconds:02d}s",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    load_local_env(SCRIPT_DIRECTORY / ".env")
    arguments = parse_arguments()
    embeddings_directory = arguments.embeddings_dir.expanduser().resolve()
    try:
        manifest_path = arguments.run_manifest.expanduser().resolve()
        manifest = read_manifest(manifest_path)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if arguments.execute and not read_api_key(arguments.api_key_env):
        print(f"Error: set {arguments.api_key_env} before using --execute.", file=sys.stderr)
        return 1
    if arguments.mock and "mock" not in arguments.collection.lower():
        arguments.collection = f"{arguments.collection}_mock"

    documents = manifest["documents"]
    requested_collection = arguments.collection
    publish_aliases = bool(arguments.execute and str(manifest.get("scope") or "FULL") == "FULL")
    if publish_aliases:
        from municipal_rag.indexing import versioned_name
        arguments.collection = versioned_name("municipal_evidence_v3", str(manifest.get("runId") or "run"))
    restore_retryable_database_documents(documents)
    ready_documents = [document for document in documents if document.get("status") == "READY"]
    chunk_entries: list[tuple[dict[str, Any], Path]] = []
    for document in ready_documents:
        chunks_value = document.get("chunks")
        if not isinstance(chunks_value, str):
            add_document_failure(document, 6, "chunk", "CHUNK_PATH_MISSING", "READY document has no chunk path.")
            continue
        chunk_path = resolve_managed_path(chunks_value)
        if not chunk_path.is_file():
            add_document_failure(document, 6, "chunk", "CHUNK_FILE_MISSING", f"Chunk file does not exist: {chunk_path}")
            continue
        chunk_entries.append((document, chunk_path))
    print(
        f"[database] {len(chunk_entries):,} production-ready documents are eligible.",
        file=sys.stderr,
        flush=True,
    )

    if not arguments.execute and not arguments.mock:
        database_summary = {
            "mode": "dry-run",
            "collection": arguments.collection,
            "eligibleDocuments": len(chunk_entries),
            "embeddedDocuments": 0,
            "generatedEmbeddingDocuments": 0,
            "reusedEmbeddingDocuments": 0,
            "importedDocuments": 0,
            "failedDocuments": 0,
            "expectedPoints": None,
            "actualPoints": None,
            "missingPoints": None,
            "stalePointsRemoved": None,
            "consistent": None,
        }
        manifest["database"] = database_summary
        manifest["completedAt"] = utc_now()
        atomic_replace_json(manifest_path, manifest)
        refresh_review_outputs(manifest_path)
        print(json.dumps(database_summary, ensure_ascii=False, indent=2))
        return 0

    state_path = embeddings_directory / STATE_FILENAME
    state = read_json(state_path)
    results: list[dict[str, Any]] = []
    embedding_jobs: list[tuple[dict[str, Any], Path, str, Path | None, bool]] = []
    for document, chunk_path in chunk_entries:
        try:
            cache_key = embedding_cache_key(chunk_path, arguments.model, arguments.mock)
            cached = state["embeddings"].get(cache_key)
            embedding_path = Path(cached["output"]) if isinstance(cached, dict) else None
            if embedding_path is None or not embedding_path.is_file():
                embedding_path = find_compatible_embeddings(
                    chunk_path, embeddings_directory, arguments.model, arguments.mock
                )
            if embedding_path is not None and embedding_path.is_file():
                state["embeddings"][cache_key] = {
                    "chunks": str(chunk_path),
                    "output": str(embedding_path.resolve()),
                    "model": arguments.model,
                }
            embedding_jobs.append((document, chunk_path, cache_key, embedding_path, False))
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
            add_document_failure(document, 7, "embedding", "CHUNK_PREPARATION_FAILED", str(error))
            document["embeddingStatus"] = "FAILED"
            results.append({"documentId": document.get("documentId"), "status": "failed", "stage": 7})
    atomic_write_json(state_path, state)

    generation_futures: dict[Any, tuple[dict[str, Any], Path, str]] = {}
    completed_embeddings: list[tuple[dict[str, Any], Path, Path, bool]] = []
    embedding_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=arguments.embedding_workers) as executor:
        for document, chunk_path, cache_key, embedding_path, _ in embedding_jobs:
            if embedding_path is not None and embedding_path.is_file():
                completed_embeddings.append((document, chunk_path, embedding_path.resolve(), False))
                continue
            future = executor.submit(
                run_with_retry,
                lambda path=chunk_path: generate_embeddings(
                    path, embeddings_directory, arguments.model, arguments.execute, arguments.mock
                ),
                arguments.retries,
            )
            generation_futures[future] = (document, chunk_path, cache_key)
        embedding_completed = len(completed_embeddings)
        emit_phase_progress(
            "embeddings", embedding_completed, len(embedding_jobs), embedding_started, force=True
        )
        for future in as_completed(generation_futures):
            document, chunk_path, cache_key = generation_futures[future]
            try:
                generation = future.result()
                embedding_path = Path(generation["output"]).resolve()
                state["embeddings"][cache_key] = {
                    "chunks": str(chunk_path),
                    "output": str(embedding_path),
                    "model": generation.get("model"),
                }
                atomic_write_json(state_path, state)
                completed_embeddings.append((document, chunk_path, embedding_path, True))
            except Exception as error:
                add_document_failure(document, 7, "embedding", "EMBEDDING_FAILED", str(error))
                document["embeddingStatus"] = "FAILED"
                results.append({"documentId": document.get("documentId"), "status": "failed", "stage": 7})
            embedding_completed += 1
            emit_phase_progress(
                "embeddings", embedding_completed, len(embedding_jobs), embedding_started
            )

    emit_phase_progress(
        "embeddings", embedding_completed, len(embedding_jobs), embedding_started, force=True
    )

    completed_embeddings.sort(key=lambda item: str(item[0].get("documentId", "")))
    imported_documents = 0
    imported_points = 0
    global_import_error: str | None = None
    import_started = time.monotonic()
    import_completed = 0
    emit_phase_progress("qdrant", 0, len(completed_embeddings), import_started, force=True)
    for document, chunk_path, embedding_path, generated in completed_embeddings:
        if document.get("status") != "READY":
            continue
        document["embeddingStatus"] = "READY"
        document["embeddings"] = managed_relative(embedding_path)
        try:
            imported = run_with_retry(
                lambda: import_embeddings(
                    chunk_path,
                    embedding_path,
                    arguments.collection,
                    arguments.qdrant_path,
                    arguments.qdrant_url,
                    arguments.qdrant_api_key_env,
                ),
                arguments.retries,
            )
            document["databaseStatus"] = "IMPORTED"
            imported_documents += 1
            imported_points += int(imported.get("importedPoints") or 0)
            results.append({
                "documentId": document.get("documentId"),
                "status": "imported",
                "embeddingsGenerated": generated,
                "importedPoints": imported.get("importedPoints"),
            })
        except Exception as error:
            add_document_failure(document, 8, "qdrant_import", "QDRANT_IMPORT_FAILED", str(error))
            document["databaseStatus"] = "FAILED"
            results.append({"documentId": document.get("documentId"), "status": "failed", "stage": 8})
            if is_global_qdrant_error(error):
                global_import_error = str(error)
        import_completed += 1
        emit_phase_progress("qdrant", import_completed, len(completed_embeddings), import_started)

    emit_phase_progress(
        "qdrant", import_completed, len(completed_embeddings), import_started, force=True
    )

    if global_import_error is not None:
        manifest["database"] = {
            "mode": "execute" if arguments.execute else "mock",
            "collection": arguments.collection,
            "eligibleDocuments": len(chunk_entries),
            "embeddedDocuments": len(completed_embeddings),
            "generatedEmbeddingDocuments": sum(item[3] for item in completed_embeddings),
            "reusedEmbeddingDocuments": sum(not item[3] for item in completed_embeddings),
            "importedDocuments": imported_documents,
            "failedDocuments": sum(
                (document.get("failedStage") or {}).get("number") in {7, 8}
                for document in documents
            ),
            "importedPoints": imported_points,
            "consistent": False,
            "globalError": global_import_error,
        }
        persist_manifest(manifest_path, manifest)
        print(f"Error: Qdrant import failed globally: {global_import_error}", file=sys.stderr)
        return 1

    try:
        print("[database] Reconciling expected and actual Qdrant points...", file=sys.stderr, flush=True)
        reconciliation = reconcile_collection(
            documents,
            str(manifest.get("scope") or "FULL"),
            arguments.collection,
            arguments.qdrant_path,
            arguments.qdrant_url,
            arguments.qdrant_api_key_env,
        )
    except Exception as error:
        manifest["database"] = {
            "mode": "execute" if arguments.execute else "mock",
            "collection": arguments.collection,
            "eligibleDocuments": len(chunk_entries),
            "embeddedDocuments": len(completed_embeddings),
            "generatedEmbeddingDocuments": sum(item[3] for item in completed_embeddings),
            "reusedEmbeddingDocuments": sum(not item[3] for item in completed_embeddings),
            "importedDocuments": imported_documents,
            "failedDocuments": sum(
                (document.get("failedStage") or {}).get("number") in {7, 8}
                for document in documents
            ),
            "importedPoints": imported_points,
            "consistent": False,
            "globalError": str(error),
        }
        persist_manifest(manifest_path, manifest)
        print(f"Error: Qdrant reconciliation failed: {error}", file=sys.stderr)
        return 1
    database_summary = {
        "mode": "execute" if arguments.execute else "mock",
        "collection": arguments.collection,
        "eligibleDocuments": len(chunk_entries),
        "embeddedDocuments": len(completed_embeddings),
        "generatedEmbeddingDocuments": sum(item[3] for item in completed_embeddings),
        "reusedEmbeddingDocuments": sum(not item[3] for item in completed_embeddings),
        "importedDocuments": imported_documents,
        "failedDocuments": sum(
            (document.get("failedStage") or {}).get("number") in {7, 8}
            for document in documents
        ),
        "importedPoints": imported_points,
        **reconciliation,
    }
    if publish_aliases and reconciliation["consistent"]:
        from municipal_rag.indexing import build_catalog_and_publish, versioned_name
        client = qdrant_client_for(arguments.qdrant_path, arguments.qdrant_url, arguments.qdrant_api_key_env)
        try:
            publication = build_catalog_and_publish(
                client, arguments.collection, requested_collection,
                versioned_name("municipal_catalog_v3", str(manifest.get("runId") or "run")),
                "municipal_catalog_current",
            )
        finally:
            client.close()
        database_summary.update(publication)
        database_summary["physicalCollection"] = arguments.collection
        database_summary["collection"] = requested_collection
    if not reconciliation["consistent"]:
        database_summary["globalError"] = "Qdrant point IDs do not match the current run manifest."
        manifest["database"] = database_summary
        persist_manifest(manifest_path, manifest)
        print(f"Error: {database_summary['globalError']}", file=sys.stderr)
        return 1
    manifest["database"] = database_summary
    persist_manifest(manifest_path, manifest)
    output: dict[str, Any] = database_summary
    if arguments.verbose:
        output = {**database_summary, "results": sorted(results, key=lambda item: str(item.get("documentId", "")))}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
