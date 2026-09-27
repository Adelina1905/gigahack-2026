from __future__ import annotations

import sys
import unittest
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_fakes import RecordingRag
from municipal_rag.chat_service import ChatService, LlmUnavailableError


CITATION = {"id": "S1", "evidenceId": "e1", "documentId": "doc-1", "versionId": "v1", "title": "Decizia 1",
            "url": "https://example.md/d1", "exactQuote": "Textul exact", "locator": {"page": 2}}


class ChatServiceTests(unittest.TestCase):
    def test_no_index_fails_instead_of_answering_without_documents(self) -> None:
        rag = RecordingRag(available=False)
        with self.assertRaises(LlmUnavailableError) as raised:
            ChatService(rag).reply("Bună", [])
        self.assertEqual(rag.questions, [])
        self.assertEqual(str(raised.exception), "The municipal document index is not available")

    def test_supported_rag_answer_maps_citations(self) -> None:
        rag = RecordingRag(True, {"status": "SUPPORTED", "answer": "Răspuns [S1]", "citations": [CITATION]})
        reply = ChatService(rag).reply("Întrebare?", [])
        self.assertEqual(rag.questions, ["Întrebare?"])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "SUPPORTED", "Răspuns [S1]"))
        self.assertEqual(reply.citations, [{
            "id": "S1", "evidenceId": "e1", "versionId": "v1", "title": "Decizia 1",
            "url": "https://example.md/d1", "exactQuote": "Textul exact",
            "documentId": "doc-1", "sourceFile": None, "locator": {"page": 2},
        }])
        self.assertIsNone(reply.clarification_choices)

    def test_needs_clarification_returns_question_choices_and_cited_documents(self) -> None:
        choices = [{"documentId": "doc-1", "label": "Decizia 1"}, {"documentId": "b", "label": "Proiect B"}]
        rag = RecordingRag(True, {"status": "NEEDS_CLARIFICATION", "answer": None, "citations": [CITATION],
                                  "clarificationQuestion": "Vă referiți la unul dintre acestea?", "clarificationChoices": choices})
        reply = ChatService(rag).reply("proiectul", [])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "NEEDS_CLARIFICATION", "Vă referiți la unul dintre acestea?"))
        self.assertEqual(reply.clarification_choices, choices)
        self.assertEqual([item["documentId"] for item in reply.citations], ["doc-1"])

    def test_not_found_says_so_instead_of_falling_back(self) -> None:
        rag = RecordingRag(True, {"status": "NOT_FOUND", "answer": "Informația nu a fost găsită", "citations": []})
        reply = ChatService(rag).reply("Q", [])
        self.assertEqual((reply.mode, reply.status, reply.answer, reply.citations), ("rag", "NOT_FOUND", "Informația nu a fost găsită", []))

    def test_unavailable_rag_becomes_llm_unavailable_with_reason(self) -> None:
        rag = RecordingRag(True, {"status": "UNAVAILABLE", "answer": None, "citations": [],
                                  "confidence": {"reasons": ["boom"]}})
        with self.assertRaises(LlmUnavailableError) as raised:
            ChatService(rag).reply("Q", [])
        self.assertEqual(str(raised.exception), "boom")


if __name__ == "__main__":
    unittest.main()
