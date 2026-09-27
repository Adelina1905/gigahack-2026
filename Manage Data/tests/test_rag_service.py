from __future__ import annotations

import sys
import unittest
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

from qdrant_client import QdrantClient, models

from municipal_rag.config import load_config
from municipal_rag.rag_service import QdrantRagService


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class QdrantRagServiceAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.alias = self.config.evidence_alias
        self.client = QdrantClient(":memory:")
        self.clock = FakeClock()

    def tearDown(self) -> None:
        self.client.close()

    def service(self) -> QdrantRagService:
        return QdrantRagService(self.client, self.config, "http://unused", clock=self.clock, cache_seconds=60.0)

    def create_collection(self, name: str, points: int) -> None:
        self.client.create_collection(name, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        if points:
            self.client.upsert(name, [models.PointStruct(id=index + 1, vector=[1.0, 0.5], payload={}) for index in range(points)])

    def point_alias(self, collection: str) -> None:
        self.client.update_collection_aliases(change_aliases_operations=[
            models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection, alias_name=self.alias))])

    def test_missing_alias_is_unavailable(self) -> None:
        self.create_collection("evidence_v1", 1)
        self.assertFalse(self.service().is_available())

    def test_alias_to_empty_collection_is_unavailable(self) -> None:
        self.create_collection("evidence_v1", 0)
        self.point_alias("evidence_v1")
        self.assertFalse(self.service().is_available())

    def test_alias_to_populated_collection_is_available(self) -> None:
        self.create_collection("evidence_v1", 1)
        self.point_alias("evidence_v1")
        self.assertTrue(self.service().is_available())

    def test_unavailable_is_cached_briefly_and_available_for_the_full_period(self) -> None:
        service = self.service()
        self.assertFalse(service.is_available())
        self.create_collection("evidence_v1", 1)
        self.point_alias("evidence_v1")
        self.clock.now += 4
        self.assertFalse(service.is_available())
        self.clock.now += 1
        self.assertTrue(service.is_available())
        self.client.delete_collection("evidence_v1")
        self.clock.now += 59
        self.assertTrue(service.is_available())
        self.clock.now += 1
        self.assertFalse(service.is_available())

    def test_client_errors_count_as_unavailable(self) -> None:
        self.client.close()
        broken = QdrantClient(url="http://127.0.0.1:1", timeout=1, check_compatibility=False)
        service = QdrantRagService(broken, self.config, "http://127.0.0.1:1", clock=self.clock)
        with self.assertLogs("municipal_rag.rag_service", level="WARNING"):
            self.assertFalse(service.is_available())


class ScriptedClient:
    """Hand-written Qdrant client: each probe step pops the next scripted outcome (a value or an exception)."""

    def __init__(self, alias: str) -> None:
        self.alias = alias
        self.outcomes: list[object] = []
        self.exact: list[bool] = []

    def next(self) -> object:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_aliases(self) -> object:
        names = self.next()
        return type("Aliases", (), {"aliases": [type("Alias", (), {"alias_name": name})() for name in names]})()

    def count(self, collection_name: str, exact: bool) -> object:
        self.exact.append(exact)
        return type("Count", (), {"count": self.next()})()


class TransientProbeErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.clock = FakeClock()
        self.client = ScriptedClient(self.config.evidence_alias)
        self.service = QdrantRagService(self.client, self.config, "http://unused", clock=self.clock)

    def test_timeout_after_success_keeps_available_and_retries_soon(self) -> None:
        self.client.outcomes = [[self.config.evidence_alias], 5]
        self.assertTrue(self.service.is_available())
        self.assertEqual(self.client.exact, [False])
        self.clock.now += 60
        self.client.outcomes = [TimeoutError("timed out")]
        with self.assertLogs("municipal_rag.rag_service", level="WARNING"):
            self.assertTrue(self.service.is_available())
        self.clock.now += 4
        self.assertTrue(self.service.is_available())
        self.assertEqual(self.client.outcomes, [])
        self.clock.now += 1
        self.client.outcomes = [[self.config.evidence_alias], 5]
        self.assertTrue(self.service.is_available())
        self.assertEqual(self.client.outcomes, [])

    def test_missing_alias_reports_unavailable_even_after_success(self) -> None:
        self.client.outcomes = [[self.config.evidence_alias], 5]
        self.assertTrue(self.service.is_available())
        self.clock.now += 60
        self.client.outcomes = [["other_alias"]]
        self.assertFalse(self.service.is_available())

    def test_error_without_a_known_good_state_is_unavailable_briefly(self) -> None:
        self.client.outcomes = [ConnectionError("refused")]
        with self.assertLogs("municipal_rag.rag_service", level="WARNING"):
            self.assertFalse(self.service.is_available())
        self.clock.now += 5
        self.client.outcomes = [[self.config.evidence_alias], 1]
        self.assertTrue(self.service.is_available())


if __name__ == "__main__":
    unittest.main()
