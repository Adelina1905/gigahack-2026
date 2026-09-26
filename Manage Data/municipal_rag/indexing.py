from __future__ import annotations

import re
import uuid
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


def build_catalog_and_publish(client: QdrantClient, evidence_collection: str, evidence_alias: str, catalog_collection: str, catalog_alias: str) -> dict[str, Any]:
    documents: dict[str, dict[str, Any]] = {}
    offset = None
    while True:
        points, offset = client.scroll(evidence_collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        for point in points:
            payload = point.payload or {}
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
        points.append(models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-document:{document_id}")), vector={"sparse": models.SparseVector(indices=indices, values=values)}, payload={"documentId": document_id, **metadata}))
    if points:
        client.upsert(catalog_collection, points=points, wait=True)
    replace_alias(client, evidence_alias, evidence_collection)
    replace_alias(client, catalog_alias, catalog_collection)
    return {"evidenceCollection": evidence_collection, "evidenceAlias": evidence_alias, "catalogCollection": catalog_collection, "catalogAlias": catalog_alias, "catalogDocuments": len(points)}

