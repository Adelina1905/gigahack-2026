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
            "url": "https://example.md/d1", "exactQuote": "Textul exact", "locator": {"page": 2},
            "publisher": "actelocale.gov.md", "publishedDate": "2026-03-18", "retrieval": {"rerankScore": .9}}


class ChatServiceTests(unittest.TestCase):
    def test_no_index_fails_instead_of_answering_without_documents(self) -> None:
        rag = RecordingRag(available=False)
        with self.assertRaises(LlmUnavailableError) as raised:
            ChatService(rag).reply("Bună", [])
        self.assertEqual(rag.questions, [])
        self.assertEqual(str(raised.exception), "The municipal document index is not available")

    def test_supported_rag_answer_maps_citations(self) -> None:
        rag = RecordingRag(True, {"status": "SUPPORTED", "answer": "Răspuns [S1]", "citations": [CITATION],
                                  "reason": None, "flags": ["DUPLICATES_MERGED:1"]})
        reply = ChatService(rag).reply("Întrebare?", [])
        self.assertEqual(rag.questions, ["Întrebare?"])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "SUPPORTED", "Răspuns [S1]"))
        self.assertEqual(reply.citations, [{
            "id": "S1", "evidenceId": "e1", "versionId": "v1", "title": "Decizia 1",
            "url": "https://example.md/d1", "exactQuote": "Textul exact",
            "documentId": "doc-1", "sourceFile": None, "locator": {"page": 2},
            "publisher": "actelocale.gov.md", "publishedDate": "2026-03-18", "outdated": False,
        }])
        self.assertIsNone(reply.clarification_choices)
        self.assertEqual((reply.reason, reply.flags), (None, ["DUPLICATES_MERGED:1"]))

    def test_history_is_passed_to_rag_for_follow_ups(self) -> None:
        history = [{"role": "user", "content": "Programul DGETS?"}, {"role": "assistant", "content": "Luni-vineri [S1]"}]
        rag = RecordingRag(True, {"status": "SUPPORTED", "answer": "Da [S1]", "citations": [CITATION]})
        ChatService(rag).reply("Și sâmbăta?", history)
        self.assertEqual(rag.histories, [history])

    def test_outdated_citation_flag_is_kept(self) -> None:
        rag = RecordingRag(True, {"status": "SUPPORTED", "answer": "Răspuns [S1]", "flags": ["OUTDATED_SOURCES"],
                                  "citations": [{**CITATION, "outdated": True}]})
        reply = ChatService(rag).reply("Q", [])
        self.assertTrue(reply.citations[0]["outdated"])
        self.assertEqual(reply.flags, ["OUTDATED_SOURCES"])

    def test_needs_clarification_returns_question_choices_and_cited_documents(self) -> None:
        choices = [{"documentId": "doc-1", "label": "Decizia 1"}, {"documentId": "b", "label": "Proiect B"}]
        rag = RecordingRag(True, {"status": "NEEDS_CLARIFICATION", "answer": None, "citations": [CITATION],
                                  "clarificationQuestion": "Vă referiți la unul dintre acestea?", "clarificationChoices": choices})
        reply = ChatService(rag).reply("proiectul", [])
        self.assertEqual((reply.mode, reply.status, reply.answer), ("rag", "NEEDS_CLARIFICATION", "Vă referiți la unul dintre acestea?"))
        self.assertEqual(reply.clarification_choices, choices)
        self.assertEqual([item["documentId"] for item in reply.citations], ["doc-1"])
        self.assertEqual((reply.reason, reply.flags), (None, []))

    def test_not_found_says_so_instead_of_falling_back(self) -> None:
        rag = RecordingRag(True, {"status": "NOT_FOUND", "answer": "Informația nu a fost găsită", "citations": [],
                                  "reason": "EVIDENCE_LACKS_VALUE", "flags": ["OFF_TOPIC_DROPPED:2"]})
        reply = ChatService(rag).reply("Q", [])
        self.assertEqual((reply.mode, reply.status, reply.answer, reply.citations), ("rag", "NOT_FOUND", "Informația nu a fost găsită", []))
        self.assertEqual((reply.reason, reply.flags), ("EVIDENCE_LACKS_VALUE", ["OFF_TOPIC_DROPPED:2"]))

    def test_not_found_never_carries_citations_and_always_has_a_contract_reason(self) -> None:
        rag = RecordingRag(True, {"status": "NOT_FOUND", "answer": "Nu", "citations": [CITATION], "reason": "SOMETHING_ELSE"})
        reply = ChatService(rag).reply("Q", [])
        self.assertEqual((reply.citations, reply.reason), ([], "NO_RELEVANT_EVIDENCE"))

    def test_contradiction_reason_and_no_reason_for_answers(self) -> None:
        contradiction = ChatService(RecordingRag(True, {"status": "CONTRADICTION", "answer": "A [S1]\nB [S2]", "citations": [CITATION]})).reply("Q", [])
        self.assertEqual(contradiction.reason, "CONFLICTING_DOCUMENTS")
        partial = ChatService(RecordingRag(True, {"status": "PARTIAL", "answer": "A [S1]", "reason": "X", "citations": [CITATION]})).reply("Q", [])
        self.assertIsNone(partial.reason)

    def test_unavailable_rag_becomes_llm_unavailable_with_reason(self) -> None:
        rag = RecordingRag(True, {"status": "UNAVAILABLE", "answer": None, "citations": [],
                                  "confidence": {"reasons": ["boom"]}})
        with self.assertRaises(LlmUnavailableError) as raised:
            ChatService(rag).reply("Q", [])
        self.assertEqual(str(raised.exception), "boom")


if __name__ == "__main__":
    unittest.main()
