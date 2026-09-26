from __future__ import annotations

from collections import Counter, OrderedDict
from threading import Lock
from typing import Any

from qdrant_client import QdrantClient, models


class SourcePreviewNotFound(Exception):
    pass


class SourcePreviewUnavailable(Exception):
    pass


class QdrantSourcePreviewService:
    """Reads immutable, pre-extracted source passages. It never fetches source URLs."""

    def __init__(self, client: QdrantClient, collection: str, cache_size: int = 64) -> None:
        self._client = client
        self._collection = collection
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[str, str], list[dict[str, Any]]] = OrderedDict()
        self._lock = Lock()

    def _scroll(self, document_id: str, version_id: str | None) -> list[dict[str, Any]]:
        conditions = [models.FieldCondition(key="documentId", match=models.MatchValue(value=document_id))]
        if version_id:
            conditions.append(models.FieldCondition(key="versionId", match=models.MatchValue(value=version_id)))
        points: list[dict[str, Any]] = []
        offset = None
        try:
            while True:
                batch, offset = self._client.scroll(
                    self._collection,
                    scroll_filter=models.Filter(must=conditions),
                    limit=256,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points.extend(point.payload or {} for point in batch)
                if offset is None:
                    break
        except Exception as error:
            raise SourcePreviewUnavailable(str(error)) from error
        return points

    def _document(self, document_id: str, version_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        if version_id:
            key = (document_id, version_id)
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return version_id, cached

        payloads = self._scroll(document_id, version_id)
        if not payloads:
            raise SourcePreviewNotFound(document_id)
        selected_version = version_id
        if not selected_version:
            counts = Counter(str(item.get("versionId") or "") for item in payloads)
            selected_version = max(counts, key=lambda value: (counts[value], value))
            payloads = [item for item in payloads if str(item.get("versionId") or "") == selected_version]
        payloads.sort(key=lambda item: (int(item.get("order", 0)), str(item.get("passageId") or "")))
        key = (document_id, selected_version)
        with self._lock:
            self._cache[key] = payloads
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return selected_version, payloads

    def preview(self, document_id: str, version_id: str | None, focus_evidence_id: str | None,
                start: int | None, limit: int) -> dict[str, Any]:
        selected_version, payloads = self._document(document_id, version_id)
        focus_index = next((index for index, item in enumerate(payloads)
                            if focus_evidence_id in (item.get("evidenceIds") or [])), None)
        if start is None:
            start = max(0, (focus_index or 0) - limit // 3)
        start = min(max(0, start), max(0, len(payloads) - 1))
        window = payloads[start:start + limit]
        first = payloads[0]
        return {
            "documentId": document_id,
            "versionId": selected_version,
            "title": first.get("title") or document_id,
            "sourceUrl": first.get("sourceUrl"),
            "sourceFile": first.get("sourceFile"),
            "sourceKind": first.get("sourceKind") or "text",
            "publishedDate": first.get("publishedDate"),
            "totalSections": len(payloads),
            "start": start,
            "focusIndex": focus_index,
            "focusSectionId": None if focus_index is None else payloads[focus_index].get("passageId"),
            "hasPrevious": start > 0,
            "hasNext": start + len(window) < len(payloads),
            "sections": [{
                "id": str(item.get("passageId") or item.get("order")),
                "order": int(item.get("order", 0)),
                "headingPath": [str(value) for value in item.get("headingPath") or []],
                "text": str(item.get("text") or ""),
                "locator": item.get("locator") or {},
            } for item in window],
        }
