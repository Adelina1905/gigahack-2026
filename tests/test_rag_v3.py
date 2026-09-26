import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "Manage Data"
sys.path.insert(0, str(ROOT))

from municipal_rag.evidence import build_evidence, split_exact
from municipal_rag.retrieval import group_documents, rrf
from municipal_rag.verification import deterministic_issues


class RagV3Tests(unittest.TestCase):
    def test_title_is_not_a_citation(self):
        document = {"documentId": "d", "documentType": "webpage", "language": "ro", "title": "Titlu distinct",
            "source": {"sha256": "v", "sourceUrl": "https://example.test", "originalFilename": "x.json"},
            "passages": [{"passageId": "p", "type": "paragraph", "citationText": "Corpul articolului conține dovada exactă necesară.", "searchText": "x", "provenance": {"kind": "api_page"}, "validation": {"overallStatus": "READY"}}]}
        evidence = build_evidence(document)
        self.assertEqual(evidence[0]["citationText"], "Corpul articolului conține dovada exactă necesară.")
        self.assertNotIn("Titlu distinct", evidence[0]["citationText"])
        self.assertIn("Titlu distinct", evidence[0]["retrievalText"])

    def test_numeric_cross_document_claim_is_rejected(self):
        evidence = {"S1": {"documentId": "a", "exactQuote": "60 mln lei"}, "S2": {"documentId": "b", "exactQuote": "proiectul X"}}
        issues = deterministic_issues({"text": "Proiectul X costă 60 mln lei", "evidenceIds": ["S1", "S2"]}, evidence)
        self.assertIn("CROSS_DOCUMENT_NUMERIC_CLAIM", issues)

    def test_headline_alone_cannot_support_claim(self):
        evidence = {"S1": {"documentId": "a", "exactQuote": "Titlu", "evidenceKind": "headline"}}
        self.assertIn("HEADLINE_ONLY", deterministic_issues({"text": "Titlu", "evidenceIds": ["S1"]}, evidence))

    def test_question_echo_cannot_pass_as_a_claim(self):
        evidence = {"S1": {"documentId": "a", "exactQuote": "Au fost 73 de accese.", "evidenceKind": "body"}}
        self.assertEqual(deterministic_issues({"text": "Câte accese au fost?", "evidenceIds": ["S1"]}, evidence), ["CLAIM_IS_NOT_DECLARATIVE"])
        self.assertEqual(deterministic_issues({"text": "Câte accese au fost 73", "evidenceIds": ["S1"]}, evidence, "Câte accese au fost?"), ["CLAIM_ECHOES_QUESTION"])

    def test_rrf_and_document_cap(self):
        a = SimpleNamespace(id="a", payload={"documentId": "d1"})
        b = SimpleNamespace(id="b", payload={"documentId": "d1"})
        c = SimpleNamespace(id="c", payload={"documentId": "d2"})
        self.assertEqual(len(group_documents(rrf([a, b, c], [c, a]), 1)), 2)

    def test_hard_split_preserves_substrings(self):
        text = " ".join([f"Propoziția {index}." for index in range(100)])
        parts = split_exact(text, 40)
        self.assertGreater(len(parts), 1)
        for quote, start, end in parts:
            self.assertEqual(quote, text[start:end])


if __name__ == "__main__":
    unittest.main()
