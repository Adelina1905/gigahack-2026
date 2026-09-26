from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


MANAGE_DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGE_DATA))

import vectorize_prepared_data as vectorizer


class FakeCollectionClient:
    def __init__(self):
        self.create_arguments = None
        self.info = None

    def collection_exists(self, _name):
        return self.info is not None

    def create_collection(self, **kwargs):
        from types import SimpleNamespace

        self.create_arguments = kwargs
        self.info = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=kwargs["vectors_config"],
                    sparse_vectors=kwargs["sparse_vectors_config"],
                ),
                hnsw_config=kwargs["hnsw_config"],
            )
        )

    def get_collection(self, _name):
        return self.info


class FastVectorizerTests(unittest.TestCase):
    def test_server_collection_is_disk_backed_and_sharded(self):
        client = FakeCollectionClient()

        vectorizer.ensure_collection(
            client, "server-collection", 4096, server_mode=True, shard_number=2
        )

        arguments = client.create_arguments
        self.assertTrue(arguments["vectors_config"]["dense"].on_disk)
        self.assertTrue(
            arguments["sparse_vectors_config"]["sparse"].index.on_disk
        )
        self.assertTrue(arguments["on_disk_payload"])
        self.assertEqual(arguments["shard_number"], 2)
        self.assertTrue(arguments["hnsw_config"].on_disk)
        self.assertEqual(arguments["hnsw_config"].max_indexing_threads, 2)
        self.assertEqual(arguments["optimizers_config"].max_optimization_threads, 2)

    def test_qdrant_retry_recovers_from_transient_disconnect(self):
        attempts = []

        def operation():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("Stream removed (End of TCP stream)")
            return "ok"

        original_sleep = vectorizer.time.sleep
        original_random = vectorizer.random.random
        vectorizer.time.sleep = lambda _seconds: None
        vectorizer.random.random = lambda: 0.0
        try:
            result = vectorizer.qdrant_with_retry(operation, 3, "test")
        finally:
            vectorizer.time.sleep = original_sleep
            vectorizer.random.random = original_random

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)

    def test_embedding_batches_respect_input_and_token_limits(self):
        values = [
            vectorizer.MissingEmbedding(str(index), f"text {index}", tokens)
            for index, tokens in enumerate((200, 300, 400, 100, 250))
        ]

        batches = vectorizer.make_embedding_batches(values, max_inputs=2, max_tokens=600)

        self.assertEqual([[item.tokens for item in batch] for batch in batches], [
            [200, 300], [400, 100], [250]
        ])

    def test_vector_binary_round_trip(self):
        original = [0.25, -0.5, 1.0, 3.125]

        restored = vectorizer.blob_to_vector(
            vectorizer.vector_to_blob(original), len(original)
        )

        for expected, actual in zip(original, restored, strict=True):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_sqlite_cache_is_keyed_by_model_and_text_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            connection = vectorizer.open_state(Path(temporary) / "state.sqlite")
            try:
                vectorizer.store_vectors(connection, "model-a", {"hash-1": [1.0, 2.0]})

                found = vectorizer.cached_vectors(
                    connection, "model-a", ["hash-1", "missing"]
                )
                other_model = vectorizer.cached_vectors(
                    connection, "model-b", ["hash-1"]
                )

                self.assertEqual(set(found), {"hash-1"})
                self.assertEqual(vectorizer.blob_to_vector(found["hash-1"][1], 2), [1.0, 2.0])
                self.assertEqual(other_model, {})
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
