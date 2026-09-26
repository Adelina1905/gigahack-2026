from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from municipal_rag.indexing import _publish_previews
from municipal_rag.source_preview import QdrantSourcePreviewService, SourcePreviewNotFound


class FakeQdrant:
    def __init__(self, payloads=None) -> None:
        self.payloads = list(payloads or [])
        self.collections = set()
        self.indexes = []
        self.upserts = []

    def collection_exists(self, collection):
        return collection in self.collections

    def create_collection(self, collection, **_kwargs):
        self.collections.add(collection)

    def get_collection(self, _collection):
        return SimpleNamespace(payload_schema={})

    def create_payload_index(self, **kwargs):
        self.indexes.append(kwargs["field_name"])

    def upsert(self, _collection, points, **_kwargs):
        self.upserts.extend(points)

    def scroll(self, _collection, scroll_filter=None, **_kwargs):
        payloads = self.payloads
        if scroll_filter is not None:
            for condition in scroll_filter.must:
                payloads = [item for item in payloads
                            if item.get(condition.key) == condition.match.value]
        return [SimpleNamespace(payload=item) for item in payloads], None


class SourcePreviewTests(unittest.TestCase):
    def test_reconstructs_order_focus_and_pages_for_the_requested_version(self) -> None:
        payloads = [
            {"documentId": "doc", "versionId": "v1", "passageId": "p2", "order": 1,
             "headingPath": ["Second"], "text": "later", "locator": {"page": 2},
             "evidenceIds": ["e2"], "title": "Document", "sourceKind": "pdf"},
            {"documentId": "doc", "versionId": "v1", "passageId": "p1", "order": 0,
             "headingPath": ["First"], "text": "focused quotation", "locator": {"page": 1},
             "evidenceIds": ["e1"], "title": "Document", "sourceKind": "pdf"},
            {"documentId": "doc", "versionId": "old", "passageId": "old", "order": 0,
             "headingPath": [], "text": "historical", "locator": {}, "evidenceIds": ["old-e"],
             "title": "Document", "sourceKind": "text"},
        ]
        result = QdrantSourcePreviewService(FakeQdrant(payloads), "previews").preview(
            "doc", "v1", "e1", None, 1)
        self.assertEqual(result["versionId"], "v1")
        self.assertEqual(result["focusIndex"], 0)
        self.assertEqual(result["focusSectionId"], "p1")
        self.assertEqual([item["id"] for item in result["sections"]], ["p1"])
        self.assertTrue(result["hasNext"])

    def test_unknown_document_is_not_found(self) -> None:
        with self.assertRaises(SourcePreviewNotFound):
            QdrantSourcePreviewService(FakeQdrant(), "previews").preview(
                "missing", None, None, None, 40)

    def test_publication_uses_stable_ids_and_reassembles_split_fragments(self) -> None:
        base = {
            "documentId": "doc", "versionId": "v1", "passageIds": ["passage-1"],
            "metadata": {"title": "Document", "sourceFile": "document.pdf",
                         "sourceUrl": "https://example.com/document.pdf"},
        }
        payloads = [
            {**base, "evidenceId": "e2", "citationText": "second",
             "sourceLocator": {"page": 4, "charStart": 20}},
            {**base, "evidenceId": "e1", "citationText": "first",
             "sourceLocator": {"page": 4, "charStart": 0}},
        ]
        client = FakeQdrant()
        self.assertEqual(_publish_previews(client, "previews", payloads), 1)
        self.assertEqual(set(client.indexes), {"documentId", "versionId"})
        point = client.upserts[0]
        self.assertEqual(point.id, str(uuid.uuid5(
            uuid.NAMESPACE_URL, "municipal-preview:doc:v1:passage-1")))
        self.assertEqual(point.payload["text"], "first second")
        self.assertEqual(point.payload["sourceKind"], "pdf")


if __name__ == "__main__":
    unittest.main()
