from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any, Sequence


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - server extras not installed
    TestClient = None

from chat_fakes import RecordingLlm, RecordingRag
from municipal_rag.alerts import (
    EMBEDDING_ENCODING, AlertService, EmbeddingMatcher, FeedDocument, JsonUpdateFeed, KeywordTopicExtractor,
    LexicalMatcher, LlmTopicExtractor, StaticUpdateFeed, Topic, TopicQuery, decode_vector, encode_vector,
    finalize_topics, normalize,
)
from municipal_rag.chat_service import ChatService


def document(document_id: str, title: str, embedding: Sequence[float] | None, excerpt: str = "") -> FeedDocument:
    return FeedDocument(document_id, title, f"https://example.md/{document_id}", "example.md", "Centru",
                        "mobility", "2026-09-01", excerpt or title, None if embedding is None else tuple(embedding))


# Unit vectors in 3D: the "transport" direction is (1, 0, 0).
FEED = StaticUpdateFeed([
    document("bus", "Ruta nouă de troleibuz pe strada Albișoara", [1.0, 0.0, 0.0]),
    document("bus2", "Modificarea orarului autobuzelor", [0.8, 0.6, 0.0]),
    document("school", "Înscrierea copiilor la grădiniță", [0.0, 1.0, 0.0]),
    document("heat", "Pornirea agentului termic", [0.0, 0.0, 1.0]),
])


class FakeEmbedder:
    """Hand-written embedder: fixed vectors per query, records calls, optionally fails."""

    def __init__(self, vectors: dict[str, list[float]], error: Exception | None = None) -> None:
        self.vectors = vectors
        self.error = error
        self.calls: list[str] = []

    def __call__(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return self.vectors[text]


class FakeExtractor:
    def __init__(self, topics: list[Topic]) -> None:
        self.topics = topics
        self.calls: list[tuple[list[str], list[str]]] = []

    def extract(self, questions: Sequence[str], existing_labels: Sequence[str]) -> list[Topic]:
        self.calls.append((list(questions), list(existing_labels)))
        return finalize_topics(self.topics, existing_labels)


class FakeCompleter:
    def __init__(self, value: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((system, user, schema))
        if self.error is not None:
            raise self.error
        return dict(self.value or {})


VECTORS = {"transport": [1.0, 0.0, 0.0], "gradinita": [0.0, 1.0, 0.0], "mix": [0.6, 0.8, 0.0]}


def service(embedder: FakeEmbedder | None = None, extractor: FakeExtractor | None = None) -> AlertService:
    embedding = None if embedder is None else EmbeddingMatcher(FEED, embedder, default_threshold=0.7)
    return AlertService(FEED, extractor or FakeExtractor([]), LexicalMatcher(FEED), embedding)


class EmbeddingMatchTests(unittest.TestCase):
    def test_default_threshold_filters_and_sorts(self) -> None:
        result = service(FakeEmbedder(VECTORS)).match([TopicQuery("t1", "transport")], [], 20)
        self.assertEqual(result.matcher, "embedding")
        self.assertEqual([(item.document.document_id, item.score) for item in result.matches],
                         [("bus", 1.0), ("bus2", 0.8)])

    def test_min_score_overrides_default_threshold(self) -> None:
        stricter = service(FakeEmbedder(VECTORS)).match([TopicQuery("t1", "transport", 0.9)], [], 20)
        self.assertEqual([item.document.document_id for item in stricter.matches], ["bus"])
        looser = service(FakeEmbedder(VECTORS)).match([TopicQuery("t1", "gradinita", 0.5)], [], 20)
        self.assertEqual([item.document.document_id for item in looser.matches], ["school", "bus2"])

    def test_one_entry_per_document_with_best_topic(self) -> None:
        topics = [TopicQuery("t1", "transport"), TopicQuery("t2", "mix", 0.0)]
        result = service(FakeEmbedder(VECTORS)).match(topics, [], 20)
        ids = [item.document.document_id for item in result.matches]
        self.assertEqual(len(ids), len(set(ids)))
        by_id = {item.document.document_id: item for item in result.matches}
        self.assertEqual(by_id["bus"].topic_id, "t1")
        self.assertEqual(by_id["bus2"].topic_id, "t2")  # mix scores 0.96 > transport's 0.8
        self.assertAlmostEqual(by_id["bus2"].score, 0.96, places=3)
        self.assertEqual(by_id["heat"].score, 0.0)  # Negative/orthogonal cosine is clamped to 0.

    def test_exclusions_and_limit(self) -> None:
        topics = [TopicQuery("t1", "mix", 0.0)]
        result = service(FakeEmbedder(VECTORS)).match(topics, ["bus2"], 2)
        self.assertEqual([item.document.document_id for item in result.matches], ["school", "bus"])

    def test_query_embeddings_are_cached(self) -> None:
        embedder = FakeEmbedder(VECTORS)
        alerts = service(embedder)
        alerts.match([TopicQuery("a", "transport"), TopicQuery("b", " transport ")], [], 20)
        alerts.match([TopicQuery("a", "transport")], [], 20)
        self.assertEqual(embedder.calls, ["transport"])

    def test_embedding_failure_falls_back_to_lexical(self) -> None:
        result = service(FakeEmbedder({}, RuntimeError("down"))).match([TopicQuery("t1", "troleibuz Albisoara")], [], 20)
        self.assertEqual(result.matcher, "lexical")
        self.assertEqual([item.document.document_id for item in result.matches], ["bus"])

    def test_feed_without_embeddings_uses_lexical(self) -> None:
        feed = StaticUpdateFeed([document("bus", "Ruta nouă de troleibuz", None)])
        embedder = FakeEmbedder(VECTORS)
        alerts = AlertService(feed, FakeExtractor([]), LexicalMatcher(feed), EmbeddingMatcher(feed, embedder))
        self.assertEqual(alerts.match([TopicQuery("t", "troleibuz")], [], 5).matcher, "lexical")
        self.assertEqual(embedder.calls, [])


class LexicalMatcherTests(unittest.TestCase):
    def test_diacritic_insensitive_overlap(self) -> None:
        scores = LexicalMatcher(FEED).scores("inscrierea la gradinita")
        self.assertEqual(scores[2], 1.0)
        self.assertEqual(scores[0], 0.0)

    def test_default_threshold_selects_relevant_documents(self) -> None:
        result = service().match([TopicQuery("t", "orarul autobuzelor")], [], 20)
        self.assertEqual(result.matcher, "lexical")
        self.assertEqual([item.document.document_id for item in result.matches], ["bus2"])

    def test_body_hits_weigh_less_than_title_hits(self) -> None:
        feed = StaticUpdateFeed([document("a", "Anunț", None, excerpt="Lucrări la rețeaua de apă"),
                                 document("b", "Lucrări la rețeaua de apă", None)])
        scores = LexicalMatcher(feed).scores("rețeaua lucrări")
        self.assertLess(scores[0], scores[1])

    def test_normalize_handles_cedilla_and_comma_forms(self) -> None:
        self.assertEqual(normalize("Şcoală Școală ţară țară"), "scoala scoala tara tara")


class FeedTests(unittest.TestCase):
    def test_json_feed_round_trips_float16_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feed.json"
            path.write_text(json.dumps({"embeddingEncoding": EMBEDDING_ENCODING, "documents": [
                {"documentId": "d1", "title": "T", "url": None, "source": "s", "district": None, "category": "c",
                 "publishedDate": "2026-01-02", "excerpt": "x" * 500, "embedding": encode_vector([0.5, -0.25])},
                {"documentId": "d2", "title": "U", "excerpt": "y"},
            ]}), encoding="utf-8")
            documents = JsonUpdateFeed(path).documents()
        self.assertEqual(documents[0].embedding, (0.5, -0.25))
        self.assertLessEqual(len(documents[0].excerpt), 400)
        self.assertIsNone(documents[1].embedding)
        self.assertEqual(decode_vector(encode_vector([1.0])), (1.0,))

    def test_missing_feed_is_empty(self) -> None:
        self.assertEqual(list(JsonUpdateFeed(Path("/nonexistent/feed.json")).documents()), [])

    def test_committed_demo_feed_is_valid(self) -> None:
        documents = JsonUpdateFeed().documents()
        self.assertGreaterEqual(len(documents), 40)
        self.assertEqual(len({item.document_id for item in documents}), len(documents))
        for item in documents:
            self.assertTrue(item.title and item.excerpt)
            self.assertLessEqual(len(item.excerpt), 400)


class TopicExtractionTests(unittest.TestCase):
    def test_keyword_fallback_maps_ro_and_ru_to_romanian_themes(self) -> None:
        topics = KeywordTopicExtractor().extract(["Când vine troleibuzul?", "Когда включат отопление?"], [])
        self.assertEqual([topic.label for topic in topics], ["Transport public", "Încălzire și agent termic"])

    def test_keyword_fallback_adds_single_district(self) -> None:
        topics = KeywordTopicExtractor().extract(["Cum înscriu copilul la grădiniță în Botanica?"], [])
        self.assertEqual(topics[0].label, "Școli și grădinițe – sectorul Botanica")
        self.assertIn("Botanica", topics[0].query)

    def test_keyword_fallback_uses_question_words_when_no_theme(self) -> None:
        topics = KeywordTopicExtractor().extract(["Unde sunt câinii fără stăpân?"], [])
        self.assertEqual([topic.label for topic in topics], ["Câinii fără stăpân"])
        self.assertEqual(KeywordTopicExtractor().extract(["Где справка?"], []), [])

    def test_existing_labels_are_not_repeated(self) -> None:
        topics = KeywordTopicExtractor().extract(["troleibuz", "grădiniță"], ["transport PUBLIC"])
        self.assertEqual([topic.label for topic in topics], ["Școli și grădinițe"])

    def test_llm_topics_are_deduped_trimmed_and_capped(self) -> None:
        completer = FakeCompleter({"topics": [
            {"label": "Orarul troleibuzelor", "query": "orar troleibuz"},
            {"label": "orarul TROLEIBUZELOR", "query": "dublură"},
            {"label": "Apă caldă", "query": "apă caldă"},
            {"label": "L" * 120, "query": "q" * 400},
            {"label": "Parcări", "query": "parcare"},
            {"label": "Al cincilea", "query": "x"},
        ]})
        topics = LlmTopicExtractor(completer, KeywordTopicExtractor()).extract(["Salut"], ["apă caldă"])
        self.assertEqual(len(topics), 4)
        self.assertEqual(topics[0], Topic("Orarul troleibuzelor", "orar troleibuz"))
        self.assertNotIn("Apă caldă", [topic.label for topic in topics])
        self.assertLessEqual(len(topics[1].label), 80)
        self.assertLessEqual(len(topics[1].query), 300)
        self.assertIn("apă caldă", completer.calls[0][1])

    def test_llm_failure_uses_keyword_fallback(self) -> None:
        for completer in (FakeCompleter(error=RuntimeError("HTTP 500")), FakeCompleter({"nope": 1})):
            topics = LlmTopicExtractor(completer, KeywordTopicExtractor()).extract(["Orarul autobuzelor"], [])
            self.assertEqual([topic.label for topic in topics], ["Transport public"])


def client_for(alerts: AlertService) -> "TestClient":
    from municipal_rag.server import create_app
    return TestClient(create_app(ChatService(RecordingRag(False), RecordingLlm()), None, True, alert_service=alerts))


@unittest.skipIf(TestClient is None, "requirements-server.txt is not installed")
class AlertRoutesTests(unittest.TestCase):
    def test_topics_route_matches_contract(self) -> None:
        extractor = FakeExtractor([Topic("Transport public", "transport"), Topic("Grădinițe", "grădiniță")])
        response = client_for(service(extractor=extractor)).post(
            "/v1/alerts/topics", json={"questions": [" Când vine troleibuzul? "], "existingLabels": ["grădinițe"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"topics": [{"label": "Transport public", "query": "transport"}]})
        self.assertEqual(extractor.calls, [(["Când vine troleibuzul?"], ["grădinițe"])])

    def test_match_route_matches_contract(self) -> None:
        response = client_for(service(FakeEmbedder(VECTORS))).post("/v1/alerts/match", json={
            "topics": [{"id": "7", "query": "transport", "minScore": None}], "excludedDocumentIds": ["bus2"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"matcher": "embedding", "matches": [{
            "topicId": "7", "documentId": "bus", "title": "Ruta nouă de troleibuz pe strada Albișoara",
            "url": "https://example.md/bus", "source": "example.md", "district": "Centru", "category": "mobility",
            "publishedDate": "2026-09-01", "excerpt": "Ruta nouă de troleibuz pe strada Albișoara", "score": 1.0}]})

    def test_match_route_reports_lexical_fallback(self) -> None:
        response = client_for(service(FakeEmbedder({}, RuntimeError("down")))).post("/v1/alerts/match", json={
            "topics": [{"id": "1", "query": "grădiniță înscriere", "minScore": 0.2}], "limit": 1})
        self.assertEqual(response.json()["matcher"], "lexical")
        self.assertEqual([item["documentId"] for item in response.json()["matches"]], ["school"])

    def test_validation_errors_return_422(self) -> None:
        client = client_for(service())
        topic = {"id": "1", "query": "transport", "minScore": None}
        topics_cases = [
            {"questions": []},
            {"questions": ["   "]},
            {"questions": ["x" * 8001]},
            {"questions": ["x"] * 51},
            {"questions": ["x"], "existingLabels": ["y"] * 51},
        ]
        for body in topics_cases:
            with self.subTest(body=str(body)[:60]):
                self.assertEqual(client.post("/v1/alerts/topics", json=body).status_code, 422)
        match_cases = [
            {"topics": []},
            {"topics": [topic] * 51},
            {"topics": [{**topic, "query": ""}]},
            {"topics": [{**topic, "query": "q" * 301}]},
            {"topics": [topic], "limit": 0},
            {"topics": [topic], "limit": 51},
        ]
        for body in match_cases:
            with self.subTest(body=str(body)[:60]):
                self.assertEqual(client.post("/v1/alerts/match", json=body).status_code, 422)

    def test_default_app_without_alert_service_returns_503(self) -> None:
        from municipal_rag.server import create_app
        client = TestClient(create_app(ChatService(RecordingRag(False), RecordingLlm()), None, True))
        response = client.post("/v1/alerts/match", json={"topics": [{"id": "1", "query": "x"}]})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(client.post("/v1/chat", json={"chatId": str(uuid.uuid4()), "message": "hi"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
