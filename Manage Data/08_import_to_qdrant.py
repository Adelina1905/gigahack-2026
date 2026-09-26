"""Import step-6 chunks and matching step-7 embeddings into Qdrant."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models


DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "municipal_documents"
PAYLOAD_INDEXES = {
    "language": models.PayloadSchemaType.KEYWORD,
    "documentType": models.PayloadSchemaType.KEYWORD,
    "indexingStatus": models.PayloadSchemaType.KEYWORD,
    "targetCollection": models.PayloadSchemaType.KEYWORD,
    "metadata.publisher": models.PayloadSchemaType.KEYWORD,
    "embedding.model": models.PayloadSchemaType.KEYWORD,
}


def load_jsonl(path: Path, description: str) -> list[dict[str, Any]]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"{description} file does not exist: {source}")
    records: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid {description} JSON on line {line_number}: {error}") from error
            if not isinstance(record, dict):
                raise ValueError(f"{description} line {line_number} is not an object.")
            records.append(record)
    if not records:
        raise ValueError(f"The {description} file contains no records.")
    return records


def by_chunk_id(records: list[dict[str, Any]], description: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        chunk_id = record.get("chunkId")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"A {description} record has no chunkId.")
        if chunk_id in indexed:
            raise ValueError(f"Duplicate chunkId in {description}: {chunk_id}")
        indexed[chunk_id] = record
    return indexed


def validate_and_join(
    chunks: list[dict[str, Any]], embeddings: list[dict[str, Any]], allow_review: bool
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int, str, bool]:
    chunks_by_id = by_chunk_id(chunks, "chunks")
    embeddings_by_id = by_chunk_id(embeddings, "embeddings")
    if set(chunks_by_id) != set(embeddings_by_id):
        raise ValueError("Chunk and embedding IDs do not match.")

    dimensions: int | None = None
    model_name: str | None = None
    mock_values: set[bool] = set()
    joined: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for chunk in chunks:
        chunk_id = chunk["chunkId"]
        if chunk.get("indexingStatus") != "READY" and not allow_review:
            raise ValueError(
                f"Chunk {chunk_id} is {chunk.get('indexingStatus')}; use --allow-review "
                "only for an isolated review/test collection."
            )
        embedding = embeddings_by_id[chunk_id]
        text = chunk.get("text")
        vector = embedding.get("embedding")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Chunk {chunk_id} has no searchable text.")
        if embedding.get("textSha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            raise ValueError(f"Text hash mismatch for chunk {chunk_id}.")
        if not isinstance(vector, list) or not vector:
            raise ValueError(f"Embedding {chunk_id} has no vector.")
        if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector):
            raise ValueError(f"Embedding {chunk_id} contains invalid values.")
        if embedding.get("dimensions") != len(vector):
            raise ValueError(f"Embedding {chunk_id} has an incorrect dimensions field.")
        dimensions = dimensions or len(vector)
        if len(vector) != dimensions:
            raise ValueError("Embedding dimensions are inconsistent.")
        current_model = embedding.get("model")
        if not isinstance(current_model, str) or not current_model:
            raise ValueError(f"Embedding {chunk_id} has no model name.")
        model_name = model_name or current_model
        if current_model != model_name:
            raise ValueError("Embedding models are inconsistent.")
        mock_values.add(embedding.get("isMock") is True)
        joined.append((chunk, embedding))
    if len(mock_values) != 1 or dimensions is None or model_name is None:
        raise ValueError("Embedding records are inconsistent.")
    return joined, dimensions, model_name, mock_values.pop()


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"municipal-chunk:{chunk_id}"))


def ensure_collection(client: QdrantClient, name: str, dimensions: int) -> bool:
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
        )
        return True
    configuration = client.get_collection(name).config.params.vectors
    if isinstance(configuration, dict):
        raise ValueError("Named-vector collections are not supported by this pipeline.")
    if configuration.size != dimensions or configuration.distance != models.Distance.COSINE:
        raise ValueError(
            f"Collection {name!r} is incompatible: expected {dimensions} dimensions and cosine distance."
        )
    return False


def ensure_indexes(client: QdrantClient, collection: str) -> list[str]:
    existing = set(client.get_collection(collection).payload_schema)
    created: list[str] = []
    for field, schema in PAYLOAD_INDEXES.items():
        if field not in existing:
            client.create_payload_index(
                collection_name=collection, field_name=field, field_schema=schema, wait=True
            )
            created.append(field)
    return created


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import real or mock embeddings into Qdrant.")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument(
        "--allow-review",
        action="store_true",
        help="Permit non-production chunks. Use only with a separate review/test collection.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        if arguments.allow_review and not any(
            marker in arguments.collection.lower() for marker in ("review", "test")
        ):
            raise ValueError("--allow-review requires a collection name containing 'review' or 'test'.")
        chunks = load_jsonl(arguments.chunks, "chunks")
        embeddings = load_jsonl(arguments.embeddings, "embeddings")
        joined, dimensions, model_name, is_mock = validate_and_join(
            chunks, embeddings, arguments.allow_review
        )
        if is_mock and "mock" not in arguments.collection.lower():
            raise ValueError("Mock vectors require a collection name containing 'mock'.")
        client = QdrantClient(url=arguments.url, timeout=20)
        client.get_collections()
        collection_created = ensure_collection(client, arguments.collection, dimensions)
        indexes_created = ensure_indexes(client, arguments.collection)
        points = [
            models.PointStruct(
                id=point_id(chunk["chunkId"]),
                vector=[float(value) for value in embedding["embedding"]],
                payload={
                    **chunk,
                    "embedding": {
                        "model": embedding["model"],
                        "dimensions": embedding["dimensions"],
                        "textSha256": embedding["textSha256"],
                        "isMock": is_mock,
                    },
                },
            )
            for chunk, embedding in joined
        ]
        client.upsert(collection_name=arguments.collection, points=points, wait=True)
        stored = client.retrieve(
            collection_name=arguments.collection,
            ids=[point.id for point in points],
            with_payload=False,
            with_vectors=False,
        )
        if len(stored) != len(points):
            raise RuntimeError("Qdrant verification failed after import.")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "qdrantUrl": arguments.url,
        "collection": arguments.collection,
        "collectionCreated": collection_created,
        "model": model_name,
        "dimensions": dimensions,
        "mockData": is_mock,
        "importedPoints": len(points),
        "verifiedPoints": len(stored),
        "payloadIndexesCreated": indexes_created,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
