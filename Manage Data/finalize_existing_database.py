#!/usr/bin/env python3
"""Audit and publish an intentionally partial Qdrant corpus without embedding more data.

The durable SQLite import ledger is the authority.  By default this command is
read-only.  With ``--apply`` it removes only Qdrant points that are not present
in the completed ledger, builds the document catalog, and atomically publishes
the configured aliases.  It never calls an embedding API.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from qdrant_client import QdrantClient, models

from municipal_rag.indexing import build_catalog_and_publish, versioned_name


ROOT = Path(__file__).resolve().parent


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-chunk:{chunk_id}"))


def batches(values: list[str], size: int) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def managed_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def expected_points(
    manifest_path: Path,
    state_path: Path,
    collection: str,
) -> tuple[set[str], set[str], Counter[str], list[dict[str, Any]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = {
        str(item["documentId"]): item
        for item in manifest.get("documents", [])
        if item.get("documentId")
    }
    connection = sqlite3.connect(f"file:{state_path.as_posix()}?mode=ro", uri=True)
    try:
        imported = connection.execute(
            "SELECT document_id, signature, chunks FROM documents "
            "WHERE collection=? AND status='IMPORTED' ORDER BY document_id",
            (collection,),
        ).fetchall()
    finally:
        connection.close()

    ids: set[str] = set()
    imported_documents: set[str] = set()
    counts: Counter[str] = Counter()
    stale_ledger_documents: list[dict[str, Any]] = []
    for index, (document_id, signature, ledger_chunks) in enumerate(imported, start=1):
        item = documents.get(str(document_id))
        if not item or not isinstance(item.get("chunks"), str):
            stale_ledger_documents.append(
                {
                    "documentId": str(document_id),
                    "signature": str(signature),
                    "chunks": int(ledger_chunks),
                }
            )
            continue
        chunk_path = managed_path(str(item["chunks"]))
        if chunk_path.name != str(signature):
            raise RuntimeError(
                f"Signature mismatch for {document_id}: ledger={signature}, manifest={chunk_path.name}"
            )
        document_count = 0
        with chunk_path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                chunk_id = record.get("chunkId")
                if not chunk_id:
                    raise RuntimeError(f"Missing chunkId in {chunk_path}:{line_number}")
                identifier = point_id(str(chunk_id))
                if identifier in ids:
                    raise RuntimeError(f"Duplicate expected point ID: {identifier}")
                ids.add(identifier)
                document_count += 1
        if document_count != int(ledger_chunks):
            raise RuntimeError(
                f"Chunk-count mismatch for {document_id}: ledger={ledger_chunks}, file={document_count}"
            )
        imported_documents.add(str(document_id))
        counts[str(document_id)] = document_count
        if index % 1000 == 0 or index == len(imported):
            print(
                f"[expected] documents={index:,}/{len(imported):,} points={len(ids):,}",
                file=sys.stderr,
                flush=True,
            )
    return ids, imported_documents, counts, stale_ledger_documents


def actual_points(
    client: QdrantClient,
    collection: str,
) -> tuple[set[str], Counter[str]]:
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=2048,
            offset=offset,
            with_payload=["documentId"],
            with_vectors=False,
        )
        for point in points:
            ids.add(str(point.id))
            document_id = str((point.payload or {}).get("documentId") or "")
            counts[document_id] += 1
        if len(ids) % 100_000 < len(points) or offset is None:
            print(f"[qdrant] points={len(ids):,}", file=sys.stderr, flush=True)
        if offset is None:
            break
    return ids, counts


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--state-database", required=True, type=Path)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--alias", default="municipal_evidence_current")
    parser.add_argument("--catalog-alias", default="municipal_catalog_current")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--delete-batch", type=int, default=512)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    manifest_path = managed_path(str(args.run_manifest))
    state_path = managed_path(str(args.state_database))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("runId") or "partial")
    report_path = args.report or (
        ROOT / "data" / "10_vectorize" / run_id / "partial-finalization.json"
    )

    expected, expected_documents, expected_by_document, stale_ledger_documents = expected_points(
        manifest_path, state_path, args.collection
    )
    client = QdrantClient(url=args.qdrant_url, timeout=120, prefer_grpc=True)
    try:
        actual, actual_by_document = actual_points(client, args.collection)
        unexpected = sorted(actual - expected)
        missing = sorted(expected - actual)
        unexpected_documents = sorted(
            document_id
            for document_id in actual_by_document
            if document_id and document_id not in expected_documents
        )
        mismatched_documents = sorted(
            document_id
            for document_id in expected_documents
            if actual_by_document[document_id] != expected_by_document[document_id]
        )
        report: dict[str, Any] = {
            "status": "AUDITED",
            "applied": False,
            "runId": run_id,
            "collection": args.collection,
            "expectedDocuments": len(expected_documents),
            "expectedPoints": len(expected),
            "actualPointsBefore": len(actual),
            "missingPoints": len(missing),
            "unexpectedPoints": len(unexpected),
            "staleLedgerDocuments": stale_ledger_documents,
            "unexpectedDocuments": unexpected_documents,
            "mismatchedDocuments": mismatched_documents,
            "report": str(report_path),
        }
        write_json(report_path, report)
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if not missing else 1
        if missing:
            raise RuntimeError(
                f"Refusing to publish: {len(missing):,} ledger points are missing from Qdrant."
            )

        for index, group in enumerate(batches(unexpected, args.delete_batch), start=1):
            client.delete(
                collection_name=args.collection,
                points_selector=models.PointIdsList(points=group),
                wait=True,
            )
            print(
                f"[cleanup] batch={index:,} removed={min(index * args.delete_batch, len(unexpected)):,}/{len(unexpected):,}",
                file=sys.stderr,
                flush=True,
            )

        after = int(client.count(args.collection, exact=True).count)
        if after != len(expected):
            raise RuntimeError(
                f"Post-cleanup count mismatch: expected={len(expected):,}, actual={after:,}"
            )
        publication = build_catalog_and_publish(
            client,
            args.collection,
            args.alias,
            versioned_name("municipal_catalog_partial", run_id),
            args.catalog_alias,
        )
        report.update(
            {
                "status": "READY",
                "applied": True,
                "actualPointsAfter": after,
                "publication": publication,
            }
        )
        write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
