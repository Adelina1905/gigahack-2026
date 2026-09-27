import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "Manage Data"
sys.path.insert(0, str(ROOT))

from municipal_rag.evidence import build_evidence, split_exact
from municipal_rag.retrieval import atomic_queries, group_documents, neighboring_payloads, prioritize_atomic, requested_fact_slots, rrf
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

    def test_atomic_queries_cover_every_location_and_requested_fact(self):
        interpreted = {
            "normalizedRomanianQuery": "Compară suma, durata, numărul acceselor și stadiul lucrărilor",
            "constraints": {"locations": ["Botanica", "Buiucani", "Ciocana"],
                            "factTypes": ["financiar", "durată", "număr", "stadiu"]},
        }
        self.assertEqual(requested_fact_slots(interpreted["normalizedRomanianQuery"], interpreted["constraints"]),
                         ["amount", "duration", "count", "status"])
        queries = atomic_queries(interpreted)
        self.assertEqual(len(queries), 12)
        self.assertEqual({item["scope"] for item in queries}, {"Botanica", "Buiucani", "Ciocana"})

    def test_neighbor_expansion_uses_source_order(self):
        selected = [{"documentId": "d1", "evidenceId": "p2", "sourceLocator": {"charStart": 20}}]
        payloads = {"d1": [
            {"documentId": "d1", "evidenceId": "p3", "sourceLocator": {"charStart": 30}},
            {"documentId": "d1", "evidenceId": "p1", "sourceLocator": {"charStart": 10}},
            selected[0],
        ]}
        expanded = neighboring_payloads(selected, payloads, 3)
        self.assertEqual([item["evidenceId"] for item in expanded], ["p2", "p1", "p3"])
        self.assertEqual(expanded[1]["retrieval"]["neighborOf"], "p2")

    def test_atomic_candidate_reservation_prevents_global_rank_starvation(self):
        global_best = SimpleNamespace(id="global", payload={"documentId": "d1"})
        cell_only = SimpleNamespace(id="cell", payload={"documentId": "d2"})
        items = [
            {"point": global_best, "score": 1.0, "ranks": {"dense": 1}},
            {"point": cell_only, "score": .1, "ranks": {"atomic:0": 1}},
        ]
        selected = prioritize_atomic(items, 1, 2)
        self.assertEqual([item["point"].id for item in selected], ["cell", "global"])

    def test_hard_split_preserves_substrings(self):
        text = " ".join([f"Propoziția {index}." for index in range(100)])
        parts = split_exact(text, 40)
        self.assertGreater(len(parts), 1)
        for quote, start, end in parts:
            self.assertEqual(quote, text[start:end])


if __name__ == "__main__":
    unittest.main()
