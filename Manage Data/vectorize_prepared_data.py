"""Fast, resumable vectorization of an existing fault-isolated run manifest.

This command consumes only READY chunk files. It batches evidence across documents,
stores vectors in a compact SQLite cache, incrementally upserts Qdrant, and prints
both per-document timings and aggregate ETA information to stderr. The final stdout
value is a single JSON object so callers can safely parse it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from qdrant_client import QdrantClient, models

from batch_reporting import read_manifest
from municipal_rag.config import load_dotenv
from municipal_rag.indexing import build_catalog_and_publish, versioned_name
from municipal_rag.sparse import bm25_sparse
from pipeline_core import resolve_managed_path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_EMBEDDINGS_DIRECTORY = SCRIPT_DIRECTORY / "data" / "07_embeddings"
DEFAULT_QDRANT_PATH = SCRIPT_DIRECTORY / "data" / "08_qdrant"
DEFAULT_REPORT_DIRECTORY = SCRIPT_DIRECTORY / "data" / "10_vectorize"
DEFAULT_MODEL = "qwen/qwen3-embedding-8b"
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
PAYLOAD_INDEXES = {
    "language": models.PayloadSchemaType.KEYWORD,
    "documentType": models.PayloadSchemaType.KEYWORD,
    "indexingStatus": models.PayloadSchemaType.KEYWORD,
    "targetCollection": models.PayloadSchemaType.KEYWORD,
    "metadata.publisher": models.PayloadSchemaType.KEYWORD,
    "embedding.model": models.PayloadSchemaType.KEYWORD,
}


@dataclass
class DocumentPlan:
    document_id: str
    path: Path
    signature: str
    tier: int = 99
    chunks: int = 0
    bytes: int = 0


@dataclass
class DocumentWork:
    plan: DocumentPlan
    records: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    cache_hits: int = 0
    generated: int = 0
    started: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class MissingEmbedding:
    text_hash: str
    text: str
    tokens: int


class ApiFailure(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_api_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            stored, _ = winreg.QueryValueEx(key, name)
        return stored.strip() if isinstance(stored, str) else ""
    except (FileNotFoundError, OSError):
        return ""


def vector_to_blob(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def blob_to_vector(blob: bytes, dimensions: int) -> list[float]:
    expected = dimensions * 4
    if len(blob) != expected:
        raise ValueError(f"Vector blob has {len(blob)} bytes; expected {expected}.")
    return list(struct.unpack(f"<{dimensions}f", blob))


def open_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            model TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            vector BLOB NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (model, text_hash)
        );
        CREATE TABLE IF NOT EXISTS documents (
            collection TEXT NOT NULL,
            document_id TEXT NOT NULL,
            signature TEXT NOT NULL,
            status TEXT NOT NULL,
            chunks INTEGER NOT NULL,
            tokens INTEGER NOT NULL,
            cached_chunks INTEGER NOT NULL,
            generated_chunks INTEGER NOT NULL,
            total_seconds REAL NOT NULL,
            error TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (collection, document_id)
        );
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    return connection


def metadata_get(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def metadata_set(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    connection.commit()


def chunks_in_file(path: Path) -> int:
    count = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            count += block.count(b"\n")
    return count


def first_jsonl_record(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"First chunk is not an object: {path}")
                return value
    raise ValueError(f"Chunk file is empty: {path}")


def curation_tiers(manifest: dict[str, Any]) -> dict[str, int]:
    input_root = manifest.get("inputRoot")
    if not isinstance(input_root, str):
        return {}
    database = resolve_managed_path(input_root) / "manifest.sqlite"
    if not database.is_file():
        return {}
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        return {
            str(sha1): int(tier)
            for sha1, tier in connection.execute("SELECT sha1, tier FROM curation")
            if sha1 and tier is not None
        }
    finally:
        connection.close()


def build_plan(
    manifest: dict[str, Any],
    connection: sqlite3.Connection,
    collection: str,
    max_documents: int | None = None,
) -> tuple[list[DocumentPlan], int, int]:
    tiers = curation_tiers(manifest)
    plans: list[DocumentPlan] = []
    skipped_complete = 0
    candidates = [
        item for item in manifest.get("documents", [])
        if item.get("status") == "READY" and isinstance(item.get("chunks"), str)
    ]
    if max_documents is not None:
        candidates = candidates[:max_documents]
    started = time.monotonic()
    for index, document in enumerate(candidates, start=1):
        path = resolve_managed_path(document["chunks"])
        if not path.is_file():
            continue
        first = first_jsonl_record(path)
        source_file = str((first.get("metadata") or {}).get("sourceFile") or "")
        source_sha = Path(source_file).stem
        signature = path.name
        row = connection.execute(
            "SELECT signature, status FROM documents WHERE collection=? AND document_id=?",
            (collection, str(document["documentId"])),
        ).fetchone()
        if row and row[0] == signature and row[1] == "IMPORTED":
            skipped_complete += 1
            continue
        plans.append(DocumentPlan(
            document_id=str(document["documentId"]),
            path=path,
            signature=signature,
            tier=tiers.get(source_sha, 99),
            chunks=chunks_in_file(path),
            bytes=path.stat().st_size,
        ))
        if index % 500 == 0 or index == len(candidates):
            elapsed = max(time.monotonic() - started, 0.001)
            print(
                f"[planning] {index:,}/{len(candidates):,} documents | "
                f"{index / elapsed:.1f} docs/s",
                file=sys.stderr,
                flush=True,
            )
    plans.sort(key=lambda item: (item.tier, item.document_id))
    return plans, sum(item.chunks for item in plans), skipped_complete


def load_chunk_records(plan: DocumentPlan) -> DocumentWork:
    work = DocumentWork(plan=plan)
    seen: set[str] = set()
    with plan.path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Chunk line {line_number} is not an object: {plan.path}")
            chunk_id = value.get("chunkId")
            text = value.get("text")
            if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen:
                raise ValueError(f"Invalid or duplicate chunkId on line {line_number}: {plan.path}")
            if value.get("indexingStatus") != "READY":
                raise ValueError(f"Non-ready chunk {chunk_id} in production input.")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Chunk {chunk_id} has no text.")
            expected_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if value.get("textSha256") != expected_hash:
                raise ValueError(f"Text hash mismatch for chunk {chunk_id}.")
            seen.add(chunk_id)
            work.records.append(value)
            work.tokens += int(value.get("tokenCountEstimate") or max(1, len(text) // 4))
    if not work.records:
        raise ValueError(f"No chunks found: {plan.path}")
    return work


def groups(values: list[str], size: int = 700) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def cached_vectors(
    connection: sqlite3.Connection, model: str, hashes: Iterable[str]
) -> dict[str, tuple[int, bytes]]:
    values = list(dict.fromkeys(hashes))
    result: dict[str, tuple[int, bytes]] = {}
    for group in groups(values):
        placeholders = ",".join("?" for _ in group)
        rows = connection.execute(
            f"SELECT text_hash, dimensions, vector FROM embeddings "
            f"WHERE model=? AND text_hash IN ({placeholders})",
            [model, *group],
        )
        result.update({str(row[0]): (int(row[1]), bytes(row[2])) for row in rows})
    return result


def store_vectors(
    connection: sqlite3.Connection,
    model: str,
    values: dict[str, list[float]],
) -> None:
    now = utc_now()
    connection.executemany(
        "INSERT OR IGNORE INTO embeddings(model,text_hash,dimensions,vector,created_at) "
        "VALUES (?,?,?,?,?)",
        [
            (model, text_hash, len(vector), vector_to_blob(vector), now)
            for text_hash, vector in values.items()
        ],
    )
    connection.commit()


def import_existing_jsonl_cache(
    connection: sqlite3.Connection,
    directory: Path,
    model: str,
) -> int:
    marker = f"jsonl-cache-imported:{model}"
    if metadata_get(connection, marker) == "1":
        return 0
    files = sorted(directory.glob("embeddings__*.jsonl"))
    imported = 0
    started = time.monotonic()
    for index, path in enumerate(files, start=1):
        batch: list[tuple[str, str, int, bytes, str]] = []
        try:
            with path.open("r", encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record.get("model") != model or record.get("isMock") is True:
                        continue
                    text_hash = record.get("textSha256")
                    vector = record.get("embedding")
                    if not isinstance(text_hash, str) or not isinstance(vector, list) or not vector:
                        continue
                    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
                        continue
                    batch.append((model, text_hash, len(vector), vector_to_blob(vector), utc_now()))
                    if len(batch) >= 250:
                        connection.executemany(
                            "INSERT OR IGNORE INTO embeddings VALUES (?,?,?,?,?)", batch
                        )
                        imported += len(batch)
                        batch.clear()
                if batch:
                    connection.executemany(
                        "INSERT OR IGNORE INTO embeddings VALUES (?,?,?,?,?)", batch
                    )
                    imported += len(batch)
            connection.commit()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"[cache] skipped {path.name}: {error}", file=sys.stderr, flush=True)
        elapsed = max(time.monotonic() - started, 0.001)
        print(
            f"[cache] {index:,}/{len(files):,} files | records={imported:,} | "
            f"{index / elapsed:.2f} files/s",
            file=sys.stderr,
            flush=True,
        )
    metadata_set(connection, marker, "1")
    return imported


def make_embedding_batches(
    missing: list[MissingEmbedding], max_inputs: int, max_tokens: int
) -> list[list[MissingEmbedding]]:
    batches: list[list[MissingEmbedding]] = []
    current: list[MissingEmbedding] = []
    tokens = 0
    for item in missing:
        if current and (len(current) >= max_inputs or tokens + item.tokens > max_tokens):
            batches.append(current)
            current = []
            tokens = 0
        current.append(item)
        tokens += item.tokens
    if current:
        batches.append(current)
    return batches


def request_embeddings(
    items: list[MissingEmbedding], model: str, api_key: str, timeout: float
) -> dict[str, list[float]]:
    payload = {
        "model": model,
        "input": [item.text for item in items],
        "input_type": "search_document",
        "encoding_format": "float",
    }
    request = urllib.request.Request(
        OPENROUTER_EMBEDDINGS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "gigahack-2026-fast-vectorizer/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:1200]
        raise ApiFailure(f"OpenRouter HTTP {error.code}: {body}", error.code) from error
    except urllib.error.URLError as error:
        raise ApiFailure(f"OpenRouter connection error: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise ApiFailure("OpenRouter returned invalid JSON.") from error
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, list) or len(data) != len(items):
        raise ApiFailure(
            f"OpenRouter returned {len(data) if isinstance(data, list) else 'no'} vectors "
            f"for {len(items)} inputs."
        )
    indexed: dict[int, list[float]] = {}
    dimensions: int | None = None
    for fallback, record in enumerate(data):
        if not isinstance(record, dict):
            raise ApiFailure("OpenRouter returned a non-object embedding.")
        index = record.get("index", fallback)
        vector = record.get("embedding")
        if not isinstance(index, int) or not isinstance(vector, list) or not vector:
            raise ApiFailure("OpenRouter returned an invalid embedding record.")
        numeric = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in numeric):
            raise ApiFailure("OpenRouter returned a non-finite embedding value.")
        dimensions = dimensions or len(numeric)
        if len(numeric) != dimensions:
            raise ApiFailure("OpenRouter embedding dimensions are inconsistent.")
        indexed[index] = numeric
    if set(indexed) != set(range(len(items))):
        raise ApiFailure("OpenRouter response contains missing or duplicate indexes.")
    return {item.text_hash: indexed[index] for index, item in enumerate(items)}


def request_with_retry(
    items: list[MissingEmbedding],
    model: str,
    api_key: str,
    timeout: float,
    retries: int,
) -> dict[str, list[float]]:
    for attempt in range(retries + 1):
        try:
            return request_embeddings(items, model, api_key, timeout)
        except ApiFailure as error:
            retryable = error.status in {429, 500, 502, 503, 504} or error.status is None
            if not retryable or attempt == retries:
                raise
            time.sleep((2 ** attempt) + random.random())
    raise ApiFailure("Embedding retry loop ended unexpectedly.")


def qdrant_client(path: Path | None, url: str | None, key_name: str) -> QdrantClient:
    if url:
        return QdrantClient(
            url=url,
            api_key=read_api_key(key_name) or None,
            timeout=60,
            prefer_grpc=True,
        )
    target = (path or DEFAULT_QDRANT_PATH).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(target))


def qdrant_with_retry(action: Any, retries: int, label: str) -> Any:
    """Retry transient server disconnects while preserving idempotent writes."""
    for attempt in range(retries + 1):
        try:
            return action()
        except Exception as error:
            code = None
            code_method = getattr(error, "code", None)
            if callable(code_method):
                try:
                    code_value = code_method()
                    code = getattr(code_value, "name", str(code_value))
                except Exception:
                    code = None
            message = str(error).lower()
            retryable = code in {
                "UNAVAILABLE",
                "DEADLINE_EXCEEDED",
                "ABORTED",
                "RESOURCE_EXHAUSTED",
                "INTERNAL",
            } or any(
                fragment in message
                for fragment in (
                    "connection refused",
                    "connection reset",
                    "end of tcp stream",
                    "stream removed",
                    "temporarily unavailable",
                    "timed out",
                    "timeout",
                )
            )
            if not retryable or attempt == retries:
                raise
            delay = min(30.0, 2.0**attempt) + random.random()
            print(
                f"[qdrant-retry] {label} attempt={attempt + 1}/{retries} "
                f"delay={delay:.1f}s error={error}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"Qdrant retry loop ended unexpectedly for {label}.")


def ensure_collection(
    client: QdrantClient,
    name: str,
    dimensions: int,
    *,
    server_mode: bool = False,
    shard_number: int = 2,
) -> None:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": models.VectorParams(
                    size=dimensions,
                    distance=models.Distance.COSINE,
                    on_disk=True if server_mode else None,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=True)
                    if server_mode
                    else None,
                    modifier=models.Modifier.IDF,
                )
            },
            shard_number=shard_number if server_mode else None,
            on_disk_payload=True if server_mode else None,
            hnsw_config=models.HnswConfigDiff(
                on_disk=True,
                max_indexing_threads=2,
            )
            if server_mode
            else None,
            optimizers_config=models.OptimizersConfigDiff(
                max_optimization_threads=2,
            )
            if server_mode
            else None,
        )
    parameters = client.get_collection(name).config.params
    configuration = parameters.vectors
    dense = configuration.get("dense") if isinstance(configuration, dict) else None
    if dense is None or dense.size != dimensions:
        raise ValueError(
            f"Collection {name!r} is incompatible with {dimensions}-dimension vectors."
        )
    if server_mode and dense.on_disk is not True:
        raise ValueError(
            f"Collection {name!r} must use on-disk dense vectors for this corpus. "
            "Choose a new collection name or recreate it with on_disk=True."
        )
    if server_mode and parameters is not None:
        information = client.get_collection(name)
        if information.config.hnsw_config.on_disk is not True:
            raise ValueError(
                f"Collection {name!r} must use an on-disk HNSW index for this corpus."
            )
    sparse_configuration = parameters.sparse_vectors or {}
    sparse = sparse_configuration.get("sparse")
    if (
        server_mode
        and (
            sparse is None
            or sparse.index is None
            or sparse.index.on_disk is not True
        )
    ):
        raise ValueError(
            f"Collection {name!r} must use an on-disk sparse index for this corpus."
        )


def ensure_indexes(client: QdrantClient, collection: str) -> None:
    existing = set(client.get_collection(collection).payload_schema)
    for field, schema in PAYLOAD_INDEXES.items():
        if field not in existing:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=schema,
                wait=True,
            )


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-chunk:{chunk_id}"))


def mark_document(
    connection: sqlite3.Connection,
    collection: str,
    work: DocumentWork,
    status: str,
    elapsed: float,
    error: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO documents(
            collection,document_id,signature,status,chunks,tokens,cached_chunks,
            generated_chunks,total_seconds,error,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(collection,document_id) DO UPDATE SET
            signature=excluded.signature,status=excluded.status,chunks=excluded.chunks,
            tokens=excluded.tokens,cached_chunks=excluded.cached_chunks,
            generated_chunks=excluded.generated_chunks,total_seconds=excluded.total_seconds,
            error=excluded.error,updated_at=excluded.updated_at
        """,
        (
            collection,
            work.plan.document_id,
            work.plan.signature,
            status,
            len(work.records),
            work.tokens,
            work.cache_hits,
            work.generated,
            elapsed,
            error,
            utc_now(),
        ),
    )
    connection.commit()


def append_document_stat(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as target:
        target.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        target.flush()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch, vectorize, and incrementally import prepared READY chunks."
    )
    parser.add_argument("--run-manifest", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--qdrant-api-key-env", default="QDRANT_API_KEY")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--qdrant-url")
    location.add_argument("--qdrant-path", type=Path)
    parser.add_argument("--qdrant-shards", type=int, default=2)
    parser.add_argument("--qdrant-retries", type=int, default=12)
    parser.add_argument("--collection")
    parser.add_argument("--alias", default="municipal_evidence_current")
    parser.add_argument("--catalog-alias", default="municipal_catalog_current")
    parser.add_argument("--embedding-workers", type=int, default=8)
    parser.add_argument("--batch-inputs", type=int, default=48)
    parser.add_argument("--batch-tokens", type=int, default=12000)
    parser.add_argument("--wave-chunks", type=int, default=512)
    parser.add_argument("--upsert-points", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-runtime-minutes", type=float, default=240.0)
    parser.add_argument("--finalize-minutes", type=float, default=20.0)
    parser.add_argument("--publish-partial", action="store_true")
    parser.add_argument("--no-import-existing-cache", action="store_true")
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_DIRECTORY)
    arguments = parser.parse_args()
    if not 1 <= arguments.embedding_workers <= 32:
        parser.error("--embedding-workers must be between 1 and 32")
    if not 1 <= arguments.qdrant_shards <= 16:
        parser.error("--qdrant-shards must be between 1 and 16")
    if not 0 <= arguments.qdrant_retries <= 30:
        parser.error("--qdrant-retries must be between 0 and 30")
    if arguments.max_documents is not None and arguments.max_documents < 1:
        parser.error("--max-documents must be at least 1")
    if not 1 <= arguments.batch_inputs <= 256:
        parser.error("--batch-inputs must be between 1 and 256")
    if arguments.batch_tokens < 420:
        parser.error("--batch-tokens must be at least 420")
    if arguments.wave_chunks < arguments.batch_inputs:
        parser.error("--wave-chunks must be at least --batch-inputs")
    if arguments.finalize_minutes >= arguments.max_runtime_minutes:
        parser.error("--finalize-minutes must be less than --max-runtime-minutes")
    return arguments


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(SCRIPT_DIRECTORY / ".env")
    arguments = parse_arguments()
    api_key = "" if arguments.plan_only else read_api_key(arguments.api_key_env)
    if not arguments.plan_only and not api_key:
        print(f"Error: set {arguments.api_key_env} before vectorization.", file=sys.stderr)
        return 1

    started = time.monotonic()
    manifest_path = arguments.run_manifest.expanduser().resolve()
    try:
        manifest = read_manifest(manifest_path)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    run_id = str(manifest.get("runId") or manifest_path.parent.name)
    collection = arguments.collection or versioned_name("municipal_evidence_fast", run_id)
    report_directory = arguments.report_root.expanduser().resolve() / run_id
    state_path = report_directory / "vectorizer-state.sqlite"
    stats_path = report_directory / "document-stats.jsonl"
    summary_path = report_directory / "summary.json"
    connection = open_state(state_path)
    client: QdrantClient | None = None
    failed_documents = 0
    imported_documents = 0
    imported_points = 0
    processed_points = 0
    generated_vectors = 0
    cache_hits = 0
    api_requests = 0
    deadline_reached = False

    try:
        if not arguments.plan_only and not arguments.no_import_existing_cache:
            imported_cache = import_existing_jsonl_cache(
                connection, DEFAULT_EMBEDDINGS_DIRECTORY, arguments.model
            )
            if imported_cache:
                print(
                    f"[cache] imported {imported_cache:,} existing vector records once.",
                    file=sys.stderr,
                    flush=True,
                )

        plans, total_points, already_complete = build_plan(
            manifest, connection, collection, arguments.max_documents
        )
        total_documents = len(plans) + already_complete
        print(
            f"[plan] documents={total_documents:,} remaining={len(plans):,} "
            f"chunks={total_points:,} workers={arguments.embedding_workers} "
            f"batch={arguments.batch_inputs}/{arguments.batch_tokens}tokens",
            file=sys.stderr,
            flush=True,
        )
        if arguments.plan_only:
            summary = {
                "mode": "plan-only",
                "runId": run_id,
                "collection": collection,
                "documents": len(plans) + already_complete,
                "remainingDocuments": len(plans),
                "alreadyCompleteDocuments": already_complete,
                "chunksToProcess": total_points,
                "networkRequestsSent": 0,
                "qdrantModified": False,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        stop_submitting_at = started + (
            arguments.max_runtime_minutes - arguments.finalize_minutes
        ) * 60
        client = qdrant_client(
            arguments.qdrant_path, arguments.qdrant_url, arguments.qdrant_api_key_env
        )

        plan_index = 0
        completed_documents = already_complete
        while plan_index < len(plans):
            if time.monotonic() >= stop_submitting_at:
                deadline_reached = True
                print("[deadline] embedding window ended; finalizing imported data.", file=sys.stderr)
                break

            wave_plans: list[DocumentPlan] = []
            wave_size = 0
            while plan_index < len(plans):
                candidate = plans[plan_index]
                if wave_plans and wave_size + candidate.chunks > arguments.wave_chunks:
                    break
                wave_plans.append(candidate)
                wave_size += candidate.chunks
                plan_index += 1
                if wave_size >= arguments.wave_chunks:
                    break

            wave_started = time.monotonic()
            works: list[DocumentWork] = []
            for plan in wave_plans:
                try:
                    works.append(load_chunk_records(plan))
                except Exception as error:
                    failed_documents += 1
                    empty = DocumentWork(plan=plan)
                    mark_document(connection, collection, empty, "ERROR", 0.0, str(error))
                    append_document_stat(stats_path, {
                        "documentId": plan.document_id,
                        "status": "ERROR",
                        "error": str(error),
                        "completedAt": utc_now(),
                    })
                    completed_documents += 1

            all_records = [record for work in works for record in work.records]
            hashes = [str(record["textSha256"]) for record in all_records]
            cached = cached_vectors(connection, arguments.model, hashes)
            missing_by_hash: dict[str, MissingEmbedding] = {}
            for work in works:
                for record in work.records:
                    text_hash = str(record["textSha256"])
                    if text_hash in cached:
                        work.cache_hits += 1
                    else:
                        missing_by_hash.setdefault(text_hash, MissingEmbedding(
                            text_hash=text_hash,
                            text=str(record["text"]),
                            tokens=int(record.get("tokenCountEstimate") or max(1, len(record["text"]) // 4)),
                        ))

            missing = list(missing_by_hash.values())
            batches = make_embedding_batches(
                missing, arguments.batch_inputs, arguments.batch_tokens
            )
            generated: dict[str, list[float]] = {}
            batch_errors: dict[str, str] = {}
            if batches:
                with ThreadPoolExecutor(max_workers=arguments.embedding_workers) as executor:
                    futures: dict[Any, tuple[list[MissingEmbedding], float]] = {
                        executor.submit(
                            request_with_retry,
                            batch,
                            arguments.model,
                            api_key,
                            arguments.timeout,
                            arguments.retries,
                        ): (batch, time.monotonic())
                        for batch in batches
                    }
                    finished_batches = 0
                    for future in as_completed(futures):
                        batch, batch_started = futures[future]
                        api_requests += 1
                        finished_batches += 1
                        outcome = "ok"
                        try:
                            values = future.result()
                            generated.update(values)
                            store_vectors(connection, arguments.model, values)
                        except Exception as error:
                            outcome = "failed"
                            for item in batch:
                                batch_errors[item.text_hash] = str(error)
                        print(
                            f"[embedding-batch] {finished_batches:,}/{len(batches):,} "
                            f"inputs={len(batch):,} tokens={sum(item.tokens for item in batch):,} "
                            f"time={time.monotonic() - batch_started:.2f}s status={outcome}",
                            file=sys.stderr,
                            flush=True,
                        )

            generated_vectors += len(generated)
            cache_hits += sum(work.cache_hits for work in works)
            vector_rows = cached_vectors(connection, arguments.model, hashes)
            if vector_rows:
                dimensions = next(iter(vector_rows.values()))[0]
                qdrant_with_retry(
                    lambda: ensure_collection(
                        client,
                        collection,
                        dimensions,
                        server_mode=bool(arguments.qdrant_url),
                        shard_number=arguments.qdrant_shards,
                    ),
                    arguments.qdrant_retries,
                    "ensure collection",
                )
                qdrant_with_retry(
                    lambda: ensure_indexes(client, collection),
                    arguments.qdrant_retries,
                    "ensure payload indexes",
                )

            for work in works:
                doc_started = work.started
                missing_errors = [
                    batch_errors[str(record["textSha256"])]
                    for record in work.records
                    if str(record["textSha256"]) in batch_errors
                ]
                unavailable = [
                    record for record in work.records
                    if str(record["textSha256"]) not in vector_rows
                ]
                if missing_errors or unavailable:
                    failed_documents += 1
                    message = missing_errors[0] if missing_errors else "Embedding unavailable after generation."
                    elapsed = time.monotonic() - doc_started
                    mark_document(connection, collection, work, "ERROR", elapsed, message)
                    append_document_stat(stats_path, {
                        "documentId": work.plan.document_id,
                        "tier": work.plan.tier,
                        "status": "ERROR",
                        "chunks": len(work.records),
                        "tokens": work.tokens,
                        "seconds": round(elapsed, 3),
                        "error": message,
                        "completedAt": utc_now(),
                    })
                    completed_documents += 1
                    continue

                point_count = 0
                for offset in range(0, len(work.records), arguments.upsert_points):
                    points: list[models.PointStruct] = []
                    for record in work.records[offset : offset + arguments.upsert_points]:
                        text_hash = str(record["textSha256"])
                        dimensions, blob = vector_rows[text_hash]
                        dense = blob_to_vector(blob, dimensions)
                        sparse_indices, sparse_values = bm25_sparse(str(record["text"]))
                        points.append(models.PointStruct(
                            id=point_id(str(record["chunkId"])),
                            vector={
                                "dense": dense,
                                "sparse": models.SparseVector(
                                    indices=sparse_indices, values=sparse_values
                                ),
                            },
                            payload={
                                **record,
                                "embedding": {
                                    "model": arguments.model,
                                    "dimensions": dimensions,
                                    "textSha256": text_hash,
                                    "isMock": False,
                                },
                            },
                        ))
                    qdrant_with_retry(
                        lambda points=points: client.upsert(
                            collection_name=collection,
                            points=points,
                            wait=True,
                        ),
                        arguments.qdrant_retries,
                        f"upsert {work.plan.document_id}",
                    )
                    point_count += len(points)
                work.generated = sum(
                    str(record["textSha256"]) in generated for record in work.records
                )
                elapsed = time.monotonic() - doc_started
                mark_document(connection, collection, work, "IMPORTED", elapsed)
                imported_documents += 1
                imported_points += point_count
                processed_points += point_count
                completed_documents += 1
                stat = {
                    "documentId": work.plan.document_id,
                    "tier": work.plan.tier,
                    "status": "IMPORTED",
                    "chunks": point_count,
                    "tokens": work.tokens,
                    "cachedChunks": work.cache_hits,
                    "generatedChunks": work.generated,
                    "seconds": round(elapsed, 3),
                    "secondsPerChunk": round(elapsed / max(point_count, 1), 4),
                    "completedAt": utc_now(),
                }
                append_document_stat(stats_path, stat)
                print(
                    f"[document] {completed_documents:,}/{total_documents:,} "
                    f"{work.plan.document_id} tier={work.plan.tier} chunks={point_count:,} "
                    f"cached={work.cache_hits:,} generated={work.generated:,} "
                    f"time={elapsed:.2f}s",
                    file=sys.stderr,
                    flush=True,
                )

            elapsed_total = max(time.monotonic() - started, 0.001)
            remaining_points = max(total_points - processed_points, 0)
            rate = processed_points / elapsed_total
            eta = int(remaining_points / rate) if rate else 0
            eta_h, eta_rem = divmod(eta, 3600)
            eta_m, eta_s = divmod(eta_rem, 60)
            print(
                f"[overall] documents={completed_documents:,}/{total_documents:,} "
                f"points={processed_points:,}/{total_points:,} "
                f"rate={rate:.2f} points/s ETA={eta_h}h{eta_m:02d}m{eta_s:02d}s "
                f"wave={time.monotonic() - wave_started:.1f}s",
                file=sys.stderr,
                flush=True,
            )

        qdrant_points = 0
        consistent = False
        if client.collection_exists(collection):
            qdrant_points = int(client.count(collection, exact=True).count)
            expected_row = connection.execute(
                "SELECT COALESCE(SUM(chunks),0) FROM documents "
                "WHERE collection=? AND status='IMPORTED'",
                (collection,),
            ).fetchone()
            expected_points = int(expected_row[0] or 0)
            consistent = qdrant_points == expected_points
        else:
            expected_points = 0

        all_complete = (
            arguments.max_documents is None
            and not deadline_reached
            and plan_index >= len(plans)
            and failed_documents == 0
        )
        publication: dict[str, Any] | None = None
        if consistent and (all_complete or arguments.publish_partial) and qdrant_points:
            publication = build_catalog_and_publish(
                client,
                collection,
                arguments.alias,
                versioned_name("municipal_catalog_fast", run_id),
                arguments.catalog_alias,
            )

        summary = {
            "runId": run_id,
            "status": "SUCCESS" if all_complete and consistent else "PARTIAL_SUCCESS",
            "model": arguments.model,
            "collection": collection,
            "documents": {
                "eligible": total_documents,
                "alreadyComplete": already_complete,
                "importedThisRun": imported_documents,
                "failed": failed_documents,
                "remaining": max(total_documents - completed_documents, 0),
            },
            "vectors": {
                "generated": generated_vectors,
                "cacheHits": cache_hits,
                "apiRequests": api_requests,
                "expectedPoints": expected_points,
                "actualPoints": qdrant_points,
                "consistent": consistent,
            },
            "deadlineReached": deadline_reached,
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "stateDatabase": str(state_path),
            "documentStats": str(stats_path),
            "publication": publication,
            "readyForQuestions": bool(publication and consistent),
        }
        atomic_json(summary_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if consistent else 1
    except KeyboardInterrupt:
        print("[stopped] Checkpoint preserved; rerun the same command to resume.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
