from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))


def load_collector():
    path = MANAGE_DATA / "fetch_municipal_corpus.py"
    spec = importlib.util.spec_from_file_location("fetch_municipal_corpus", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_collector()


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def get_json(self, path: str, params: dict[str, str]):
        self.calls.append(dict(params))
        if "cursor" not in params:
            return {
                "documents": [
                    {"id": "doc-a", "updated_at": "2026-09-25T10:00:00+00:00", "pages": []}
                ],
                "next_cursor": "second-page",
            }
        return {
            "documents": [
                {"id": "doc-b", "updated_at": "2026-09-25T11:00:00+00:00", "pages": []}
            ],
            "next_cursor": None,
        }


def arguments(output_dir: Path, **overrides):
    values = {
        "output_dir": output_dir,
        "tiers": "1,2",
        "source": None,
        "category": None,
        "lang": None,
        "updated_since": None,
        "full": False,
        "include_ocr_pending": False,
        "metadata_only": False,
        "page_size": 100,
        "max_documents": None,
        "overlap_seconds": 300,
        "delay": 0,
    }
    values.update(overrides)
    return Namespace(**values)


class CorpusCollectorTests(unittest.TestCase):
    def test_collection_writes_one_immutable_file_per_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = FakeClient()
            result = collector.collect(arguments(root), client)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["snapshotsCreated"], 2)
            self.assertEqual(len(list((root / "doc-a").glob("*.json"))), 1)
            self.assertEqual(len(list((root / "doc-b").glob("*.json"))), 1)
            state = json.loads((root / collector.DEFAULT_STATE_FILENAME).read_text("utf-8"))
            self.assertNotIn("active", state)
            checkpoint = next(iter(state["checkpoints"].values()))
            self.assertEqual(
                checkpoint["last_completed_updated_at"], "2026-09-25T11:00:00+00:00"
            )

    def test_same_document_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = {"id": "safe-id", "updated_at": "2026-09-25T10:00:00+00:00"}
            first_path, first_created = collector.save_document(root, document)
            second_path, second_created = collector.save_document(root, document)
            self.assertEqual(first_path, second_path)
            self.assertTrue(first_created)
            self.assertFalse(second_created)

    def test_document_id_cannot_escape_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(collector.CollectionError):
                collector.save_document(
                    Path(temporary),
                    {"id": "../escape", "updated_at": "2026-09-25T10:00:00+00:00"},
                )

    def test_incremental_run_overlaps_last_timestamp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = arguments(root)
            base_params = collector.build_params(args, None)
            fingerprint = collector.query_fingerprint(base_params)
            collector.write_state(
                root / collector.DEFAULT_STATE_FILENAME,
                {
                    "version": collector.STATE_VERSION,
                    "checkpoints": {
                        fingerprint: {
                            "last_completed_updated_at": "2026-09-25T11:00:00+00:00",
                            "params": base_params,
                        }
                    },
                },
            )
            client = FakeClient()
            collector.collect(args, client)
            self.assertEqual(client.calls[0]["updated_since"], "2026-09-25T10:55:00+00:00")

    def test_different_filters_do_not_share_incremental_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mobility_args = arguments(root, category="mobility")
            mobility_params = collector.build_params(mobility_args, None)
            fingerprint = collector.query_fingerprint(mobility_params)
            collector.write_state(
                root / collector.DEFAULT_STATE_FILENAME,
                {
                    "version": collector.STATE_VERSION,
                    "checkpoints": {
                        fingerprint: {
                            "last_completed_updated_at": "2026-09-25T11:00:00+00:00",
                            "params": mobility_params,
                        }
                    },
                },
            )
            client = FakeClient()
            collector.collect(arguments(root, category="education"), client)
            self.assertNotIn("updated_since", client.calls[0])


if __name__ == "__main__":
    unittest.main()
