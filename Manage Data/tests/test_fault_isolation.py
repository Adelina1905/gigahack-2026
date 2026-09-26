from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

import batch_reporting
import prepare_ai_database
import run_corpus_pipeline
import run_pipeline


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def api_document(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "updated_at": "2026-09-26T10:00:00+03:00",
        "title": f"Document {document_id}",
    }


def manifest_document(document_id: str, status: str, chunks: str | None = None) -> dict[str, object]:
    return {
        "documentId": document_id,
        "title": document_id,
        "sourceSnapshot": f"Original Data/municipal_corpus/{document_id}/snapshot.json",
        "status": status,
        "pipelineStatus": status,
        "indexingDecision": "PRODUCTION" if status == "READY" else "BLOCKED",
        "chunks": chunks,
        "failedStage": None,
        "issues": [],
        "artifacts": {},
    }


class FaultIsolationTests(unittest.TestCase):
    def test_qdrant_configuration_errors_are_global(self):
        self.assertTrue(prepare_ai_database.is_global_qdrant_error(
            RuntimeError("Collection 'municipal' is incompatible: expected 16 dimensions")
        ))
        self.assertFalse(prepare_ai_database.is_global_qdrant_error(
            RuntimeError("Text hash mismatch for chunk one")
        ))

    def test_validation_warning_stops_before_chunk_generation(self):
        stages = [
            {"documentId": "warning", "manifest": "manifest.json", "snapshot": "source.json"},
            {"documentId": "warning", "output": "extracted.json", "extractionStatus": "READY"},
            {"documentId": "warning", "output": "structured.json"},
            {"documentId": "warning", "output": "enriched.json"},
            {
                "documentId": "warning",
                "output": "validated.json",
                "validation": {"overallStatus": "NEEDS_REVIEW", "indexingDecision": "REVIEW"},
            },
        ]
        arguments = Namespace(
            input=Path("source.json"),
            title=None,
            document_id="warning",
            source_url=None,
            source_type=None,
            document_type=None,
            publisher=None,
            published_date=None,
            retrieved_at=None,
            language="ro",
            max_tokens=450,
            ready_only=False,
        )
        output = StringIO()
        with (
            patch.object(run_pipeline, "parse_arguments", return_value=arguments),
            patch.object(run_pipeline, "run_stage", side_effect=stages) as run_stage,
            patch.object(run_pipeline, "validation_issues", return_value=[{
                "severity": "WARNING",
                "code": "CITATION_TEXT_SOURCE_MISMATCH",
                "stage": 5,
                "message": "citation mismatch",
                "retryable": True,
            }]),
            redirect_stdout(output),
        ):
            exit_code = run_pipeline.main()

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["outcome"], "WARNING")
        self.assertIsNone(result["chunks"])
        self.assertEqual(run_stage.call_count, 5)

    def test_malformed_folder_does_not_hide_valid_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / "good"
            bad = root / "bad"
            good.mkdir()
            bad.mkdir()
            write_json(good / "snapshot.json", api_document("good"))
            (bad / "snapshot.json").write_text("{not-json", encoding="utf-8")

            records = run_corpus_pipeline.discover_snapshot_records(root)

            self.assertEqual([record["result"]["status"] for record in records if record["result"]], ["ERROR"])
            selected = [record for record in records if record["result"] is None]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["document"]["id"], "good")

    def test_review_outputs_are_sorted_and_point_to_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            run_directory = Path(temporary) / "run-1"
            manifest_path = run_directory / "run-manifest.json"
            warning = manifest_document("b-warning", "WARNING")
            warning["issues"] = [{
                "severity": "WARNING",
                "code": "OCR_REQUIRED",
                "stage": 2,
                "message": "OCR is required",
                "retryable": True,
            }]
            warning["failedStage"] = {"number": 2, "name": "extract", "retryable": True}
            manifest = {
                "schemaVersion": 1,
                "runId": "run-1",
                "scope": "FULL",
                "startedAt": "2026-09-26T00:00:00+00:00",
                "completedAt": "2026-09-26T00:01:00+00:00",
                "documents": [warning, manifest_document("a-ready", "READY")],
                "database": None,
            }
            batch_reporting.atomic_replace_json(manifest_path, manifest)

            summary = batch_reporting.refresh_review_outputs(manifest_path)
            stored = batch_reporting.read_manifest(manifest_path)
            report = json.loads((run_directory / "documents" / "b-warning.json").read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "PARTIAL_SUCCESS")
            self.assertEqual(summary["counts"], {"discovered": 2, "ready": 1, "warning": 1, "error": 0})
            self.assertEqual([item["documentId"] for item in stored["documents"]], ["a-ready", "b-warning"])
            self.assertEqual(report["sourceSnapshot"], warning["sourceSnapshot"])
            self.assertFalse((run_directory / "documents" / "a-ready.json").exists())
            self.assertEqual(json.loads((run_directory.parent / "latest.json").read_text())["runId"], "run-1")

    def test_database_inconsistency_marks_run_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "run-2" / "run-manifest.json"
            manifest = {
                "schemaVersion": 1,
                "runId": "run-2",
                "scope": "FULL",
                "startedAt": "2026-09-26T00:00:00+00:00",
                "completedAt": "2026-09-26T00:01:00+00:00",
                "documents": [manifest_document("ready", "READY")],
                "database": {"consistent": False, "globalError": "database unavailable"},
            }
            batch_reporting.atomic_replace_json(manifest_path, manifest)

            summary = batch_reporting.refresh_review_outputs(manifest_path)

            self.assertEqual(summary["status"], "FAILED")

    def test_database_stage_failure_can_be_retried_without_losing_audit_history(self):
        document = manifest_document("retry-me", "ERROR", "chunks.jsonl")
        document["pipelineStatus"] = "READY"
        document["indexingDecision"] = "PRODUCTION"
        document["failedStage"] = {"number": 7, "name": "embedding", "retryable": True}
        document["issues"] = [{
            "severity": "ERROR",
            "code": "EMBEDDING_FAILED",
            "stage": 7,
            "message": "temporary timeout",
            "retryable": True,
        }]

        prepare_ai_database.restore_retryable_database_documents([document])

        self.assertEqual(document["status"], "READY")
        self.assertIsNone(document["failedStage"])
        self.assertEqual(document["issues"], [])
        self.assertEqual(document["attemptHistory"][0]["issues"][0]["code"], "EMBEDDING_FAILED")

    def test_malformed_chunk_is_isolated_during_embedding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_directory = root / "review" / "run-3"
            manifest_path = run_directory / "run-manifest.json"
            valid_chunks = root / "valid.jsonl"
            invalid_chunks = root / "invalid.jsonl"
            valid_chunks.write_text(json.dumps({
                "chunkId": "valid-chunk",
                "text": "valid text",
                "textSha256": "hash",
            }) + "\n", encoding="utf-8")
            invalid_chunks.write_text("{broken", encoding="utf-8")
            manifest = {
                "schemaVersion": 1,
                "runId": "run-3",
                "scope": "PARTIAL",
                "startedAt": "2026-09-26T00:00:00+00:00",
                "completedAt": None,
                "documents": [
                    manifest_document("invalid", "READY", str(invalid_chunks)),
                    manifest_document("valid", "READY", str(valid_chunks)),
                ],
                "database": None,
            }
            batch_reporting.atomic_replace_json(manifest_path, manifest)
            arguments = Namespace(
                run_manifest=manifest_path,
                chunks_dir=root,
                embeddings_dir=root / "embeddings",
                model="mock/model",
                collection="isolation_mock",
                api_key_env="OPENROUTER_API_KEY",
                qdrant_api_key_env="QDRANT_API_KEY",
                execute=False,
                mock=True,
                qdrant_url=None,
                qdrant_path=root / "qdrant",
                embedding_workers=2,
                retries=0,
                verbose=False,
            )

            def fake_generate(chunk_path, output_directory, model, execute, mock):
                output_directory.mkdir(parents=True, exist_ok=True)
                target = output_directory / f"{chunk_path.stem}.jsonl"
                target.write_text(json.dumps({
                    "chunkId": "valid-chunk",
                    "textSha256": "hash",
                    "model": "mock/model",
                    "embedding": [1.0, 0.0],
                }) + "\n", encoding="utf-8")
                return {"output": str(target), "model": "mock/model"}

            with (
                patch.object(prepare_ai_database, "parse_arguments", return_value=arguments),
                patch.object(prepare_ai_database, "generate_embeddings", side_effect=fake_generate),
                patch.object(prepare_ai_database, "import_embeddings", return_value={"importedPoints": 1}),
                patch.object(prepare_ai_database, "reconcile_collection", return_value={
                    "expectedPoints": 1,
                    "actualPoints": 1,
                    "missingPoints": 0,
                    "stalePointsRemoved": 0,
                    "consistent": True,
                }),
                redirect_stdout(StringIO()),
            ):
                exit_code = prepare_ai_database.main()

            stored = batch_reporting.read_manifest(manifest_path)
            by_id = {item["documentId"]: item for item in stored["documents"]}
            self.assertEqual(exit_code, 0)
            self.assertEqual(by_id["invalid"]["status"], "ERROR")
            self.assertEqual(by_id["invalid"]["failedStage"]["number"], 7)
            self.assertEqual(by_id["valid"]["databaseStatus"], "IMPORTED")
            self.assertTrue((run_directory / "documents" / "invalid.json").is_file())

    def test_full_reconciliation_removes_stale_points(self):
        from qdrant_client import QdrantClient, models

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            qdrant_path = root / "qdrant"
            chunks = root / "ready.jsonl"
            chunk_id = "ready-chunk"
            chunks.write_text(json.dumps({"chunkId": chunk_id}) + "\n", encoding="utf-8")
            expected_id = prepare_ai_database.chunk_point_id(chunk_id)
            stale_id = str(uuid.uuid4())
            client = QdrantClient(path=str(qdrant_path))
            client.create_collection(
                collection_name="test_collection",
                vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
            )
            client.upsert(
                collection_name="test_collection",
                points=[
                    models.PointStruct(id=expected_id, vector=[1.0, 0.0], payload={"documentId": "ready"}),
                    models.PointStruct(id=stale_id, vector=[0.0, 1.0], payload={"documentId": "warning"}),
                ],
                wait=True,
            )
            client.close()
            ready = manifest_document("ready", "READY", str(chunks))
            ready["databaseStatus"] = "IMPORTED"
            warning = manifest_document("warning", "WARNING")

            result = prepare_ai_database.reconcile_collection(
                [ready, warning], "FULL", "test_collection", qdrant_path, None, "QDRANT_API_KEY"
            )

            self.assertEqual(result["expectedPoints"], 1)
            self.assertEqual(result["actualPoints"], 1)
            self.assertEqual(result["stalePointsRemoved"], 1)
            self.assertTrue(result["consistent"])

    def test_partial_reconciliation_preserves_unselected_documents(self):
        from qdrant_client import QdrantClient, models

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            qdrant_path = root / "qdrant"
            chunks = root / "selected.jsonl"
            chunk_id = "selected-chunk"
            chunks.write_text(json.dumps({"chunkId": chunk_id}) + "\n", encoding="utf-8")
            selected_id = prepare_ai_database.chunk_point_id(chunk_id)
            unselected_id = str(uuid.uuid4())
            client = QdrantClient(path=str(qdrant_path))
            client.create_collection(
                collection_name="test_collection",
                vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
            )
            client.upsert(
                collection_name="test_collection",
                points=[
                    models.PointStruct(id=selected_id, vector=[1.0, 0.0], payload={"documentId": "selected"}),
                    models.PointStruct(id=unselected_id, vector=[0.0, 1.0], payload={"documentId": "unselected"}),
                ],
                wait=True,
            )
            client.close()
            selected = manifest_document("selected", "READY", str(chunks))
            selected["databaseStatus"] = "IMPORTED"

            result = prepare_ai_database.reconcile_collection(
                [selected], "PARTIAL", "test_collection", qdrant_path, None, "QDRANT_API_KEY"
            )
            client = QdrantClient(path=str(qdrant_path))
            stored = client.retrieve("test_collection", ids=[unselected_id], with_payload=True)
            client.close()

            self.assertEqual(result["stalePointsRemoved"], 0)
            self.assertTrue(result["consistent"])
            self.assertEqual(len(stored), 1)


if __name__ == "__main__":
    unittest.main()
