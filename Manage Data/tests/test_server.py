from __future__ import annotations

import sys
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch, sentinel


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - server extras not installed
    TestClient = None

from chat_fakes import RecordingLlm, RecordingRag
from municipal_rag.chat_service import ChatService


def client_for(rag: RecordingRag, llm: RecordingLlm, llm_configured: bool = True) -> "TestClient":
    from municipal_rag.server import create_app
    return TestClient(create_app(ChatService(rag, llm), rag, llm_configured))


@unittest.skipIf(TestClient is None, "requirements-server.txt is not installed")
class ServerTests(unittest.TestCase):
    def body(self, **overrides: object) -> dict[str, object]:
        return {"chatId": str(uuid.uuid4()), "message": "Salut", "history": [], **overrides}

    def test_health_reports_flags(self) -> None:
        response = client_for(RecordingRag(False), RecordingLlm(), llm_configured=False).get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"mode": "live", "llmConfigured": False, "ragAvailable": False})
        response = client_for(RecordingRag(True), RecordingLlm(), llm_configured=True).get("/health")
        self.assertEqual(response.json(), {"mode": "live", "llmConfigured": True, "ragAvailable": True})

    def test_chat_llm_response_matches_contract(self) -> None:
        llm = RecordingLlm("Bună ziua")
        history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        response = client_for(RecordingRag(False), llm).post("/v1/chat", json=self.body(message="  Salut  ", history=history))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"mode": "llm", "status": "LLM", "answer": "Bună ziua",
                                           "citations": [], "clarificationChoices": None})
        self.assertEqual([item["content"] for item in llm.calls[0][1:]], ["a", "b", "Salut"])

    def test_chat_rag_response_matches_contract(self) -> None:
        rag = RecordingRag(True, {"status": "PARTIAL", "answer": "Parțial [S1]", "citations": [
            {"id": "S1", "title": "Doc", "url": None, "exactQuote": "citat", "documentId": "d1", "locator": {}}]})
        response = client_for(rag, RecordingLlm()).post("/v1/chat", json=self.body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"mode": "rag", "status": "PARTIAL", "answer": "Parțial [S1]",
            "citations": [{"title": "Doc", "url": None, "exactQuote": "citat", "documentId": "d1"}],
            "clarificationChoices": None})

    def test_chat_clarification_choices(self) -> None:
        rag = RecordingRag(True, {"status": "NEEDS_CLARIFICATION", "clarificationQuestion": "Care?",
            "clarificationChoices": [{"documentId": "a", "label": "A"}], "citations": []})
        response = client_for(rag, RecordingLlm()).post("/v1/chat", json=self.body())
        self.assertEqual(response.json()["clarificationChoices"], [{"documentId": "a", "label": "A"}])
        self.assertEqual(response.json()["answer"], "Care?")

    def test_llm_failure_maps_to_503(self) -> None:
        llm = RecordingLlm(error=RuntimeError("OPENROUTER_API_KEY is not configured"))
        response = client_for(RecordingRag(False), llm).post("/v1/chat", json=self.body())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "OPENROUTER_API_KEY is not configured"})

    def test_validation_errors_return_422(self) -> None:
        client = client_for(RecordingRag(False), RecordingLlm())
        cases = [
            self.body(message="   "),
            self.body(message="x" * 8001),
            self.body(history=[{"role": "system", "content": "x"}]),
            self.body(history=[{"role": "user", "content": "x"}] * 51),
            self.body(chatId="not-a-uuid"),
        ]
        for body in cases:
            with self.subTest(body=str(body)[:80]):
                self.assertEqual(client.post("/v1/chat", json=body).status_code, 422)

    def test_demo_starts_without_keys_qdrant_or_network(self) -> None:
        from municipal_rag.server import create_default_app

        with patch.dict(os.environ, {"CHAT_MODE": "demo"}, clear=True), \
                patch("municipal_rag.server.load_dotenv"), \
                patch("municipal_rag.server.load_config", side_effect=AssertionError("live config loaded")), \
                patch.dict(sys.modules, {"qdrant_client": None}), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            client = TestClient(create_default_app())
            self.assertEqual(client.get("/health").json(),
                             {"mode": "demo", "llmConfigured": False, "ragAvailable": False})
            body = self.body(message="Salut", history=[{"role": "user", "content": "Earlier"}])
            first = client.post("/v1/chat", json=body)
            second = client.post("/v1/chat", json=body)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json(), second.json())
            self.assertEqual(first.json(), {
                "mode": "demo", "status": "DEMO",
                "answer": "Python received your message (5 characters) and "
                          "1 earlier user message(s). This deterministic reply is for checking chat "
                          "integration and saved conversations. It is not an AI answer or official "
                          "municipal information.\n\nExample link for testing: https://example.com "
                          "(demonstration only; not a supporting source).",
                "citations": [], "clarificationChoices": None,
            })
            self.assertEqual(client.post("/v1/chat", json=self.body(message="  ")).status_code, 422)
            self.assertEqual(client.post("/v1/chat", json=self.body(chatId="bad")).status_code, 422)

    def test_default_mode_uses_live_factory(self) -> None:
        from municipal_rag.server import create_default_app

        with patch.dict(os.environ, {}, clear=True), patch("municipal_rag.server.load_dotenv"), \
                patch("municipal_rag.server._create_live_app", return_value=sentinel.app) as factory:
            self.assertIs(create_default_app(), sentinel.app)
            factory.assert_called_once_with()

    def test_explicit_live_failure_does_not_fall_back_to_demo(self) -> None:
        from municipal_rag.server import create_default_app

        with patch.dict(os.environ, {"CHAT_MODE": "live"}), patch("municipal_rag.server.load_dotenv"), \
                patch("municipal_rag.server._create_live_app", side_effect=RuntimeError("live failed")):
            with self.assertRaisesRegex(RuntimeError, "live failed"):
                create_default_app()

    def test_invalid_mode_fails_fast(self) -> None:
        from municipal_rag.server import create_default_app

        for mode in ("", "automatic", "dmeo"):
            with self.subTest(mode=mode), patch.dict(os.environ, {"CHAT_MODE": mode}), \
                    patch("municipal_rag.server.load_dotenv"), \
                    patch("municipal_rag.server._create_live_app") as factory:
                with self.assertRaisesRegex(ValueError, "CHAT_MODE"):
                    create_default_app()
                factory.assert_not_called()

    def test_live_factory_without_key_returns_failure_not_demo(self) -> None:
        from municipal_rag.server import create_default_app

        with patch.dict(os.environ, {"CHAT_MODE": "live"}, clear=True), \
                patch("municipal_rag.server.load_dotenv"), \
                patch("qdrant_client.QdrantClient"), \
                patch("municipal_rag.rag_service.QdrantRagService", return_value=RecordingRag(False)), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            client = TestClient(create_default_app())
            self.assertEqual(client.get("/health").json()["mode"], "live")
            response = client.post("/v1/chat", json=self.body())
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("demo", response.text.lower())


if __name__ == "__main__":
    unittest.main()
