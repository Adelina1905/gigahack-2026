from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))


def load_script(name: str):
    path = MANAGE_DATA / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_script("pipeline_core.py")
ingest = load_script("01_ingest_source.py")
extract = load_script("02_extract_content.py")
structure = load_script("03_structure_document.py")
enrich = load_script("04_enrich_document.py")
chunking = load_script("06_create_chunks.py")
answering = load_script("10_answer_question.py")


class PipelineV2Tests(unittest.TestCase):
    def test_search_normalization_does_not_change_citation(self):
        source = "Ședința   Consiliului\nMunicipal"
        blocks = core.split_text_blocks(source)
        self.assertEqual(blocks[0]["citationText"], source)
        self.assertEqual(blocks[0]["searchText"], "Ședința Consiliului\nMunicipal")

    def test_ingestion_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("Text municipal", encoding="utf-8")
            arguments = Namespace(
                input=source,
                title="Document test",
                source_url="https://example.test/document",
                source_type="text_document",
                document_type="municipal_document",
                publisher="Primăria",
                published_date="2026-09-25",
                retrieved_at="2026-09-25T12:00:00+03:00",
                language="ro",
                manifest_dir=root / "manifests",
                source_dir=root / "sources",
            )
            first, first_path, created = ingest.ingest_source(arguments)
            second, second_path, created_again = ingest.ingest_source(arguments)
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first["documentId"], second["documentId"])
            self.assertEqual(first_path, second_path)

    def test_generic_document_does_not_turn_article_paragraphs_into_events(self):
        manifest = {
            "documentId": "doc-test",
            "title": "Articol",
            "documentType": "unknown",
            "language": "ro",
            "publisher": "Primăria",
            "publishedDate": "2024-08-23",
            "retrievedAt": "2026-09-25T12:00:00+03:00",
            "source": {"sourceType": "derived_web_text", "sourceUrl": "https://example.test"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            source_path = Path(temporary) / "article.txt"
            source_path.write_text("Un articol cu informații publice.", encoding="utf-8")
            extracted = extract.extract_text_source(manifest, source_path)
            input_path = Path(temporary) / "extracted.json"
            core.write_json(input_path, extracted)
            document = structure.structure_document(input_path)
            self.assertEqual(document["documentType"], "webpage_article")
            self.assertEqual(len(document["passages"]), 1)
            self.assertEqual(document["passages"][0]["type"], "paragraph")

    def test_multiline_spreadsheet_block_is_not_discarded_as_heading(self):
        text = "## Worksheet\nBudget municipal\nVenituri 1000 lei"
        self.assertEqual(extract.api_block_type(text), "paragraph")
        self.assertEqual(extract.api_block_type("## Worksheet"), "heading")

    def test_event_without_year_is_flagged_instead_of_guessed(self):
        passage = {
            "passageId": "passage-1",
            "type": "municipal_event",
            "citationText": "Eveniment\nLocația: Chișinău\nPerioada: 10 septembrie",
            "attributes": {"periodRaw": "10 septembrie"},
        }
        facts, warnings = enrich.normalize_event_period(passage)
        self.assertEqual(facts, [])
        self.assertIn("EVENT_YEAR_MISSING", warnings)

    def test_event_passages_are_never_merged(self):
        passages = [
            {"type": "municipal_event", "headingPath": [], "searchText": "A"},
            {"type": "municipal_event", "headingPath": [], "searchText": "B"},
        ]
        groups = chunking.group_passages(passages, 450)
        self.assertEqual([len(group) for group in groups], [1, 1])

    def test_answer_evidence_is_deduplicated(self):
        citation = {
            "passageId": "passage-1",
            "quote": "Informație municipală suficientă și direct verificabilă.",
            "sourceUrl": "https://example.test",
            "locator": {"kind": "source_lines", "startLine": 1, "endLine": 1},
        }
        response = {
            "results": [
                {
                    "score": 0.8,
                    "documentId": "doc-1",
                    "title": "Document",
                    "indexingStatus": "READY",
                    "citations": [citation],
                },
                {
                    "score": 0.7,
                    "documentId": "doc-1",
                    "title": "Document",
                    "indexingStatus": "READY",
                    "citations": [citation],
                },
            ]
        }
        evidence = answering.build_evidence(response, 0.35)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["id"], "S1")

    def test_answer_rejects_unknown_citation(self):
        evidence = [{"id": "S1"}]
        answer = {
            "answer": "Răspuns [S2].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S2"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "high",
        }
        with self.assertRaises(RuntimeError):
            answering.validate_answer(answer, evidence)

    def test_answer_accepts_matching_inline_citations(self):
        evidence = [
            {"id": "S1", "documentId": "doc-1"},
            {"id": "S2", "documentId": "doc-2"},
        ]
        answer = {
            "answer": "Prima afirmație [S1]. A doua afirmație [S2].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1", "S2"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "high",
        }
        answering.validate_answer(answer, evidence)

    def test_answer_does_not_split_at_romanian_street_abbreviation(self):
        evidence = [{"id": "S1", "documentId": "doc-1", "quote": "Lucrări pe strada Petru Rareș."}]
        answer = {
            "answer": "Au fost executate lucrări pe str. Petru Rareș [S1].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "high",
        }
        answering.validate_answer(answer, evidence)
        self.assertEqual(
            len(answering.split_answer_segments("Lucrări pe bd. Iu. Gagarin [S1].")),
            1,
        )

    def test_answer_rejects_ids_missing_from_answer_text(self):
        evidence = [{"id": "S1"}]
        answer = {
            "answer": "Afirmație fără marcaj inline.",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "medium",
        }
        with self.assertRaisesRegex(RuntimeError, "Inline citations"):
            answering.validate_answer(answer, evidence)

    def test_answer_rejects_citations_dumped_after_uncited_claims(self):
        evidence = [
            {"id": "S1", "documentId": "doc-1"},
            {"id": "S2", "documentId": "doc-2"},
        ]
        answer = {
            "answer": "Prima lucrare repară străzile municipale. A doua lucrare repară curțile [S1] [S2].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1", "S2"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "medium",
        }
        with self.assertRaisesRegex(RuntimeError, "immediate citation"):
            answering.validate_answer(answer, evidence)

    def test_partial_answer_requires_explicit_limitations(self):
        evidence = [{"id": "S1", "documentId": "doc-1"}]
        answer = {
            "answer": "Corpusul descrie doar o parte dintre lucrări [S1].",
            "informationStatus": "PARTIAL",
            "evidenceIds": ["S1"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "medium",
        }
        with self.assertRaisesRegex(RuntimeError, "must explain"):
            answering.validate_answer(answer, evidence)

    def test_numeric_sentence_cannot_mix_documents(self):
        evidence = [
            {"id": "S1", "documentId": "water-project", "quote": "Bugetul este de 60 mln lei."},
            {"id": "S2", "documentId": "yard-project", "quote": "Lucrările au costat 60 mln lei."},
        ]
        answer = {
            "answer": "Lucrările din curți au costat 60 de milioane de lei [S1] [S2].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1", "S2"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "medium",
        }
        with self.assertRaisesRegex(RuntimeError, "numeric sentence"):
            answering.validate_answer(answer, evidence)

    def test_sentence_cannot_overcite_one_document(self):
        evidence = [
            {"id": "S1", "documentId": "doc-1"},
            {"id": "S2", "documentId": "doc-1"},
        ]
        answer = {
            "answer": "Au fost reparate mai multe căi de acces [S1] [S2].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1", "S2"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "high",
        }
        with self.assertRaisesRegex(RuntimeError, "same document"):
            answering.validate_answer(answer, evidence)

    def test_numeric_claim_must_appear_in_cited_quote(self):
        evidence = [
            {"id": "S1", "documentId": "doc-1", "quote": "Contractul valorează 14 mln lei."},
        ]
        answer = {
            "answer": "Pentru lucrări au fost alocate 60 mln lei [S1].",
            "informationStatus": "SUPPORTED",
            "evidenceIds": ["S1"],
            "contradictionDetails": [],
            "limitations": [],
            "confidence": "high",
        }
        with self.assertRaisesRegex(RuntimeError, "numeric claim"):
            answering.validate_answer(answer, evidence)


if __name__ == "__main__":
    unittest.main()
