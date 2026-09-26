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


if __name__ == "__main__":
    unittest.main()
