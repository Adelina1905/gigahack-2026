from __future__ import annotations

import importlib.util
import json
import sqlite3
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
validate = load_script("05_validate_document.py")
batch = load_script("run_corpus_pipeline.py")


def api_document(updated_at: str = "2026-09-25T23:05:57+03:00"):
    return {
        "id": "0013988e003efaf8f4b9814f6dbe3b4972c47194",
        "updated_at": updated_at,
        "title": "Document municipal de test",
        "lang": "ro",
        "source": "example.md",
        "category": "mobility",
        "district": "Centru",
        "tier": 1,
        "curation_reasons": ["test"],
        "canonical_url": "https://example.test/document",
        "raw_url": "/raw/example/document.pdf",
        "doc_date": "2026-09-25",
        "content_type": "text/html",
        "extraction_method": "trafilatura",
        "status": "ok",
        "quality_flags": [],
        "ocr_pending_pages": [],
        "act": None,
        "pages": [
            {
                "page": None,
                "text": "# Titlu\n\nPrimul paragraf verificabil.\n\nAl doilea paragraf.",
                "ocr": False,
                "conf": None,
            }
        ],
    }


def scraper_document(sha1: str, *, pending_ocr: bool = False):
    return {
        "sha1": sha1,
        "source": "example.md",
        "category": "mobility",
        "district": "Centru",
        "lang": "ro",
        "title": "Document extras de scraper",
        "doc_date": "2026-09-25",
        "content_type": "application/pdf",
        "method": "pymupdf",
        "extracted_at": "2026-09-26T06:41:10+00:00",
        "urls": [{"url": "https://example.test/document.pdf"}],
        "quality_flags": ["low_ocr_conf"] if pending_ocr else [],
        "needs_ocr_pages": [2] if pending_ocr else [],
        "pages": [
            {"page": 1, "text": "Primul paragraf verificabil.", "ocr": False},
            {"page": 2, "text": "", "ocr": False},
        ],
    }


def ingest_arguments(source: Path, root: Path, document_id: str):
    return Namespace(
        input=source,
        title="Document municipal de test",
        document_id=document_id,
        source_url="https://example.test/document",
        source_type="municipal_corpus_api",
        document_type="webpage_article",
        publisher="example.md",
        published_date="2026-09-25",
        retrieved_at="2026-09-26T00:00:00+03:00",
        language="ro",
        manifest_dir=root / "01_manifests",
        source_dir=root / "01_sources",
    )


class ApiCorpusPipelineTests(unittest.TestCase):
    def test_scraper_corpus_is_discovered_without_modifying_its_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sha1 = "a" * 40
            source = root / "text" / "example.md" / f"{sha1}.json"
            source.parent.mkdir(parents=True)
            original = scraper_document(sha1)
            source.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            connection = sqlite3.connect(root / "manifest.sqlite")
            connection.execute("CREATE TABLE extracted (sha1 TEXT, status TEXT)")
            connection.execute("INSERT INTO extracted VALUES (?, ?)", (sha1, "ok"))
            connection.commit()
            connection.close()

            records = batch.discover_snapshot_records(root)

            self.assertEqual(len(records), 1)
            self.assertIsNone(records[0]["result"])
            self.assertEqual(records[0]["document"]["_corpus_format"], "chisinau_scraper_v1")
            self.assertEqual(records[0]["document"]["_extraction_status"], "ok")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8")), original)

    def test_completed_ocr_pages_are_ready_when_manifest_status_is_ok(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sha1 = "c" * 40
            source = root / "original.json"
            document = scraper_document(sha1, pending_ocr=True)
            document["n_ocr_pages"] = 1
            document["quality_flags"] = []
            source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            manifest = {
                "documentId": "completed-ocr-test",
                "title": "Document OCR finalizat",
                "language": "ro",
                "source": {"sourceType": "chisinau_scraper_snapshot"},
            }

            extracted = extract.extract_scraper_document(manifest, source, "ok")

            self.assertEqual(extracted["extraction"]["status"], "READY")
            self.assertFalse(extracted["extraction"]["requiresOcr"])

    def test_scraper_extractor_blocks_pending_ocr_but_preserves_clean_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sha1 = "b" * 40
            # Stage 1 preserves imported JSON under this neutral filename.
            source = root / "original.json"
            source.write_text(
                json.dumps(scraper_document(sha1, pending_ocr=True), ensure_ascii=False),
                encoding="utf-8",
            )
            manifest = {
                "documentId": "scraper-test",
                "title": "Document extras de scraper",
                "language": "ro",
                "source": {"sourceType": "chisinau_scraper_snapshot"},
            }

            extracted = extract.extract_scraper_document(manifest, source)

            self.assertEqual(extracted["extraction"]["status"], "OCR_REQUIRED")
            self.assertEqual(len(extracted["blocks"]), 1)
            self.assertEqual(extracted["blocks"][0]["provenance"]["page"], 1)

    def test_api_adapter_preserves_and_validates_page_citations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "api.json"
            document = api_document()
            source.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            manifest, _, _ = ingest.ingest_source(
                ingest_arguments(source, root, document["id"])
            )
            snapshot = Path(manifest["source"]["snapshotPath"])
            extracted = extract.extract_api_document(manifest, snapshot)

            self.assertEqual(extracted["extraction"]["status"], "READY")
            self.assertEqual(len(extracted["blocks"]), 3)
            self.assertEqual(extracted["blocks"][1]["provenance"]["kind"], "api_page")

            extracted_path = root / "extracted.json"
            core.write_json(extracted_path, extracted)
            structured = structure.structure_document(extracted_path)
            self.assertEqual(len(structured["passages"]), 2)
            structured_path = root / "structured.json"
            core.write_json(structured_path, structured)
            validated = validate.validate_document(structured_path)
            self.assertEqual(validated["validation"]["overallStatus"], "READY")

    def test_same_api_id_can_keep_multiple_immutable_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "api.json"
            first = api_document()
            source.write_text(json.dumps(first), encoding="utf-8")
            first_manifest, first_path, _ = ingest.ingest_source(
                ingest_arguments(source, root, first["id"])
            )

            second = api_document("2026-09-26T10:00:00+03:00")
            second["pages"][0]["text"] += "\n\nText actualizat."
            source.write_text(json.dumps(second), encoding="utf-8")
            second_manifest, second_path, _ = ingest.ingest_source(
                ingest_arguments(source, root, second["id"])
            )

            self.assertEqual(first_manifest["documentId"], second_manifest["documentId"])
            self.assertNotEqual(first_path, second_path)
            self.assertNotEqual(
                first_manifest["source"]["snapshotPath"],
                second_manifest["source"]["snapshotPath"],
            )

    def test_batch_discovery_selects_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document_id = api_document()["id"]
            directory = root / document_id
            directory.mkdir()
            old = api_document("2026-09-25T10:00:00+03:00")
            new = api_document("2026-09-26T10:00:00+03:00")
            (directory / "old.json").write_text(json.dumps(old), encoding="utf-8")
            (directory / "new.json").write_text(json.dumps(new), encoding="utf-8")

            selected = batch.discover_latest_snapshots(root)
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0][0].name, "new.json")


if __name__ == "__main__":
    unittest.main()
