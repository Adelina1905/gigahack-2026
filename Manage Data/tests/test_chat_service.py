from __future__ import annotations

import sys
import unittest
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_fakes import RecordingLlm, RecordingRag
from municipal_rag.chat_service import DEFAULT_SYSTEM_PROMPT, ChatService, LlmUnavailableError


CITATION = {"id": "S1", "evidenceId": "e1", "documentId": "doc-1", "versionId": "v1", "title": "Decizia 1",
            "url": "https://example.md/d1", "exactQuote": "Textul exact", "locator": {"page": 2}}


class ChatServiceTests(unittest.TestCase):
    def test_no_index_uses_llm_and_never_calls_rag_answer(self) -> None:
        rag, llm = RecordingRag(available=False), RecordingLlm("salut")
        reply = ChatService(rag, llm).reply("Bună", [])
        self.assertEqual(rag.questions, [])
        self.assertEqual((reply.mode, reply.status, reply.answer, reply.citations, reply.clarification_choices),
                         ("llm", "LLM", "salut", [], None))
        self.assertEqual(len(llm.calls), 1)

    def test_supported_rag_answer_maps_citations(self) -> None:
        rag = RecordingRag(True, {"status": "SUPPORTED", "answer": "Răspuns [S1]", "citations": [CITATION]})
        llm = RecordingLlm()
        reply = ChatService(rag, llm).reply("Întrebare?", [])
        self.assertEqual(rag.questions, ["Întrebare?"])
        self.assertEqual(llm.calls, [])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "SUPPORTED", "Răspuns [S1]"))
        self.assertEqual(reply.citations, [{
            "id": "S1", "evidenceId": "e1", "versionId": "v1", "title": "Decizia 1",
            "url": "https://example.md/d1", "exactQuote": "Textul exact",
            "documentId": "doc-1", "sourceFile": None, "locator": {"page": 2},
        }])
        self.assertIsNone(reply.clarification_choices)

    def test_needs_clarification_returns_question_and_choices(self) -> None:
        choices = [{"documentId": "a", "label": "Proiect A"}, {"documentId": "b", "label": "Proiect B"}]
        rag = RecordingRag(True, {"status": "NEEDS_CLARIFICATION", "answer": None, "citations": [],
                                  "clarificationQuestion": "La care proiect vă referiți?", "clarificationChoices": choices})
        llm = RecordingLlm()
        reply = ChatService(rag, llm).reply("proiectul", [])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "NEEDS_CLARIFICATION", "La care proiect vă referiți?"))
        self.assertEqual(reply.clarification_choices, choices)
        self.assertEqual(llm.calls, [])

    def test_not_found_falls_back_to_llm(self) -> None:
        rag = RecordingRag(True, {"status": "NOT_FOUND", "answer": "Informația nu a fost găsită", "citations": []})
        llm = RecordingLlm("fallback")
        reply = ChatService(rag, llm).reply("Q", [])
        self.assertEqual(rag.questions, ["Q"])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("llm", "LLM", "fallback"))

    def test_unavailable_falls_back_to_llm(self) -> None:
        rag = RecordingRag(True, {"status": "UNAVAILABLE", "answer": None, "citations": [],
                                  "confidence": {"reasons": ["boom"]}})
        llm = RecordingLlm("fallback")
        reply = ChatService(rag, llm).reply("Q", [])
        self.assertEqual((reply.mode, reply.answer), ("llm", "fallback"))
        self.assertEqual(len(llm.calls), 1)

    def test_llm_error_becomes_llm_unavailable(self) -> None:
        llm = RecordingLlm(error=RuntimeError("OPENROUTER_API_KEY is not configured"))
        with self.assertRaises(LlmUnavailableError) as raised:
            ChatService(RecordingRag(False), llm).reply("Q", [])
        self.assertEqual(str(raised.exception), "OPENROUTER_API_KEY is not configured")

    def test_history_forwarded_in_order_after_system_prompt(self) -> None:
        llm = RecordingLlm()
        history = [{"role": "user", "content": "unu"}, {"role": "assistant", "content": "doi"},
                   {"role": "system", "content": "ignored"}, {"role": "user", "content": "trei"}]
        ChatService(RecordingRag(False), llm, system_prompt="SYS").reply("patru", history)
        self.assertEqual(llm.calls[0], [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "unu"},
            {"role": "assistant", "content": "doi"},
            {"role": "user", "content": "trei"},
            {"role": "user", "content": "patru"},
        ])

    def test_default_system_prompt_is_used(self) -> None:
        llm = RecordingLlm()
        ChatService(RecordingRag(False), llm).reply("Q", [])
        self.assertEqual(llm.calls[0][0], {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})


if __name__ == "__main__":
    unittest.main()
