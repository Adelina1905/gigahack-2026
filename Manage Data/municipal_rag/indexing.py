from __future__ import annotations

import re
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from .sparse import bm25_sparse


def versioned_name(prefix: str, run_id: str) -> str:
    return f"{prefix}_{re.sub(r'[^a-zA-Z0-9_]', '_', run_id)}"


def replace_alias(client: QdrantClient, alias: str, collection: str) -> None:
    aliases = {item.alias_name for item in client.get_aliases().aliases}
    operations: list[Any] = []
    if alias in aliases:
        operations.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
    operations.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)))
    client.update_collection_aliases(operations)


def _locator_order(locator: dict[str, Any], passage_id: str) -> tuple[Any, ...]:
    def number(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10**9
    return (
        number(locator.get("page", locator.get("pageNumber"))),
        number(locator.get("startLine")),
        number(locator.get("blockIndex")),
        passage_id,
    )


def _source_kind(source_file: str) -> str:
    suffix = Path(source_file).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".html", ".htm"}:
        return "web"
    return "text"


def _publish_previews(client: QdrantClient, collection: str, payloads: list[dict[str, Any]]) -> int:
    if not client.collection_exists(collection):
        client.create_collection(collection, vectors_config={})
    schema = set(client.get_collection(collection).payload_schema)
    for field in ("documentId", "versionId"):
        if field not in schema:
            client.create_payload_index(collection_name=collection, field_name=field,
                                        field_schema=models.PayloadSchemaType.KEYWORD, wait=True)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for payload in payloads:
        document_id = str(payload.get("documentId") or "")
        version_id = str(payload.get("versionId") or "")
        locator = payload.get("sourceLocator") or {}
        passage_ids = payload.get("passageIds") or []
        passage_id = str(passage_ids[0] if passage_ids else locator.get("passageId") or payload.get("evidenceId") or "")
        if document_id and version_id and passage_id:
            grouped[(document_id, version_id, passage_id)].append(payload)

    by_document: dict[tuple[str, str], list[tuple[str, list[dict[str, Any]]]]] = defaultdict(list)
    for (document_id, version_id, passage_id), fragments in grouped.items():
        by_document[(document_id, version_id)].append((passage_id, fragments))

    points: list[models.PointStruct] = []
    for (document_id, version_id), passages in by_document.items():
        passages.sort(key=lambda item: _locator_order(item[1][0].get("sourceLocator") or {}, item[0]))
        for order, (passage_id, fragments) in enumerate(passages):
            fragments.sort(key=lambda item: int((item.get("sourceLocator") or {}).get("charStart", 0)))
            first = fragments[0]
            metadata = first.get("metadata") or {}
            locator = first.get("sourceLocator") or {}
            text = " ".join(str(item.get("citationText") or "").strip() for item in fragments).strip()
            if not text:
                continue
            source_file = str(metadata.get("sourceFile") or "")
            preview = {
                "documentId": document_id,
                "versionId": version_id,
                "passageId": passage_id,
                "order": order,
                "headingPath": metadata.get("heading") or [],
                "text": text,
                "locator": locator,
                "evidenceIds": [str(item.get("evidenceId") or item.get("chunkId")) for item in fragments],
                "title": metadata.get("title") or document_id,
                "sourceUrl": metadata.get("sourceUrl"),
                "sourceFile": source_file,
                "sourceKind": _source_kind(source_file),
                "publishedDate": metadata.get("publishedDate"),
            }
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-preview:{document_id}:{version_id}:{passage_id}"))
            points.append(models.PointStruct(id=point_id, vector={}, payload=preview))
    for offset in range(0, len(points), 256):
        client.upsert(collection, points=points[offset : offset + 256], wait=True)
    return len(points)


def build_catalog_and_publish(client: QdrantClient, evidence_collection: str, evidence_alias: str,
                              catalog_collection: str, catalog_alias: str,
                              preview_collection: str = "municipal_source_previews") -> dict[str, Any]:
    documents: dict[str, dict[str, Any]] = {}
    evidence_payloads: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(evidence_collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        for point in points:
            payload = point.payload or {}
            evidence_payloads.append(payload)
            document_id = payload.get("documentId")
            if document_id:
                documents.setdefault(str(document_id), payload)
        if offset is None:
            break
    if client.collection_exists(catalog_collection):
        client.delete_collection(catalog_collection)
    client.create_collection(catalog_collection, vectors_config={}, sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)})
    points = []
    for document_id, payload in sorted(documents.items()):
        metadata = payload.get("metadata") or {}
        text = " | ".join(str(value) for value in (metadata.get("title"), metadata.get("publisher"), metadata.get("category"), metadata.get("district")) if value)
        indices, values = bm25_sparse(text)
        points.append(models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-document:{document_id}")), vector={"sparse": models.SparseVector(indices=indices, values=values)}, payload={"documentId": document_id, "versionId": payload.get("versionId"), **metadata}))
    for offset in range(0, len(points), 512):
        client.upsert(catalog_collection, points=points[offset : offset + 512], wait=True)
    replace_alias(client, evidence_alias, evidence_collection)
    replace_alias(client, catalog_alias, catalog_collection)
    preview_sections = _publish_previews(client, preview_collection, evidence_payloads)
    return {"evidenceCollection": evidence_collection, "evidenceAlias": evidence_alias, "catalogCollection": catalog_collection, "catalogAlias": catalog_alias, "catalogDocuments": len(points), "previewCollection": preview_collection, "previewSections": preview_sections}
