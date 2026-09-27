"""Build source-preview records from an existing municipal evidence index."""

from __future__ import annotations

import argparse

from qdrant_client import QdrantClient, models

from municipal_rag.indexing import _publish_previews


def scroll_payloads(
    client: QdrantClient,
    collection: str,
    scroll_filter: models.Filter | None = None,
) -> list[dict]:
    payloads: list[dict] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection,
            scroll_filter=scroll_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        payloads.extend(point.payload or {} for point in points)
        if offset is None:
            return payloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--evidence", default="municipal_evidence_current")
    parser.add_argument("--catalog", default="municipal_catalog_current")
    parser.add_argument("--preview", default="municipal_source_previews")
    parser.add_argument("--batch-documents", type=int, default=100)
    parser.add_argument(
        "--document-id",
        action="append",
        dest="document_ids",
        help="Backfill only this document ID; repeat for multiple documents",
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.batch_documents < 1:
        parser.error("--batch-documents must be positive")

    client = QdrantClient(url=args.qdrant_url, timeout=60)
    if args.replace and client.collection_exists(args.preview):
        client.delete_collection(args.preview)

    if args.document_ids:
        document_ids = sorted(set(args.document_ids))
    else:
        catalog = scroll_payloads(client, args.catalog)
        document_ids = sorted({
            str(payload.get("documentId"))
            for payload in catalog
            if payload.get("documentId")
        })
    total_sections = 0
    for start in range(0, len(document_ids), args.batch_documents):
        batch = document_ids[start:start + args.batch_documents]
        evidence_filter = models.Filter(must=[models.FieldCondition(
            key="documentId",
            match=models.MatchAny(any=batch),
        )])
        payloads = scroll_payloads(client, args.evidence, evidence_filter)
        total_sections += _publish_previews(client, args.preview, payloads)
        completed = min(start + len(batch), len(document_ids))
        print(
            f"documents={completed}/{len(document_ids)} "
            f"evidence={len(payloads)} previewSections={total_sections}",
            flush=True,
        )

    print({
        "documents": len(document_ids),
        "previewCollection": args.preview,
        "previewSections": total_sections,
    })


if __name__ == "__main__":
    main()
