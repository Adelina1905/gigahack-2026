"""Generate OpenRouter embeddings for prepared municipal-data chunks.

Dry-run is the default and performs no network request. To call OpenRouter,
pass ``--execute`` and provide the API key through the
``OPENROUTER_API_KEY`` environment variable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_API_KEY_ENVIRONMENT_VARIABLE = "OPENROUTER_API_KEY"
DEFAULT_OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "data" / "embeddings"
MOCK_MODEL = "mock/example-only-not-for-search"
MOCK_DIMENSIONS = 16


def load_chunks(input_path: Path) -> list[dict[str, Any]]:
    """Load and validate the JSONL chunks produced by step 6."""
    source = input_path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Chunk file does not exist: {source}")

    chunks: list[dict[str, Any]] = []
    chunk_ids: set[str] = set()

    with source.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {error}"
                ) from error

            if not isinstance(chunk, dict):
                raise ValueError(
                    f"Chunk on line {line_number} is not a JSON object."
                )

            chunk_id = chunk.get("chunkId")
            text = chunk.get("text")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise ValueError(f"Chunk on line {line_number} has no chunkId.")
            if chunk_id in chunk_ids:
                raise ValueError(f"Duplicate chunkId: {chunk_id}")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Chunk {chunk_id} has no searchable text.")

            chunk_ids.add(chunk_id)
            chunks.append(chunk)

    if not chunks:
        raise ValueError("The input file contains no chunks.")

    return chunks


def build_request_payload(
    chunks: list[dict[str, Any]], model: str
) -> dict[str, Any]:
    """Build the OpenRouter request without sending it."""
    return {
        "model": model,
        "input": [chunk["text"] for chunk in chunks],
        "input_type": "search_document",
        "encoding_format": "float",
    }


def request_embeddings(
    payload: dict[str, Any], api_key: str, timeout_seconds: float
) -> dict[str, Any]:
    """Send one embeddings request to OpenRouter."""
    request = urllib.request.Request(
        OPENROUTER_EMBEDDINGS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "gigahack-2026-municipal-data/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=timeout_seconds
        ) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(
            f"OpenRouter returned HTTP {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach OpenRouter: {error.reason}") from error

    try:
        decoded = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenRouter returned invalid JSON.") from error

    if not isinstance(decoded, dict):
        raise RuntimeError("OpenRouter returned an unexpected response shape.")
    return decoded


def validate_embeddings(
    response: dict[str, Any], expected_count: int
) -> list[list[float]]:
    """Validate count, order, dimensions, and numeric values."""
    data = response.get("data")
    if not isinstance(data, list):
        raise RuntimeError("OpenRouter response has no data list.")
    if len(data) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} embeddings but received {len(data)}."
        )

    indexed_embeddings: dict[int, list[float]] = {}
    expected_dimensions: int | None = None

    for fallback_index, item in enumerate(data):
        if not isinstance(item, dict):
            raise RuntimeError("OpenRouter returned a non-object embedding item.")

        index = item.get("index", fallback_index)
        embedding = item.get("embedding")
        if not isinstance(index, int) or index < 0 or index >= expected_count:
            raise RuntimeError(f"Invalid embedding index: {index}")
        if index in indexed_embeddings:
            raise RuntimeError(f"Duplicate embedding index: {index}")
        if not isinstance(embedding, list) or not embedding:
            raise RuntimeError(f"Embedding {index} is empty or invalid.")
        if not all(
            isinstance(value, (int, float)) and math.isfinite(float(value))
            for value in embedding
        ):
            raise RuntimeError(f"Embedding {index} contains a non-finite value.")

        numeric_embedding = [float(value) for value in embedding]
        if expected_dimensions is None:
            expected_dimensions = len(numeric_embedding)
        elif len(numeric_embedding) != expected_dimensions:
            raise RuntimeError("Embedding dimensions are inconsistent.")

        indexed_embeddings[index] = numeric_embedding

    if set(indexed_embeddings) != set(range(expected_count)):
        raise RuntimeError("OpenRouter response is missing one or more indices.")

    return [indexed_embeddings[index] for index in range(expected_count)]


def create_embedding_records(
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    requested_model: str,
    response_model: Any,
) -> list[dict[str, Any]]:
    """Attach each vector to a stable chunk reference."""
    dimensions = len(embeddings[0])
    model_used = response_model if isinstance(response_model, str) else requested_model
    records: list[dict[str, Any]] = []

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        records.append(
            {
                "chunkId": chunk["chunkId"],
                "textSha256": hashlib.sha256(
                    chunk["text"].encode("utf-8")
                ).hexdigest(),
                "model": model_used,
                "dimensions": dimensions,
                "embedding": embedding,
            }
        )

    return records


def create_mock_embedding(text: str) -> list[float]:
    """Create a deterministic example vector that is not suitable for search."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big")
    generator = random.Random(seed)
    return [round(generator.uniform(-1.0, 1.0), 6) for _ in range(MOCK_DIMENSIONS)]


def serialize_jsonl(records: list[dict[str, Any]]) -> bytes:
    lines = [
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def safe_model_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-_") or "model"


def write_once(target: Path, content: bytes) -> bool:
    """Write atomically, refusing to overwrite different existing content."""
    if target.exists():
        if target.read_bytes() != content:
            raise RuntimeError(f"Existing output has unexpected content: {target}")
        return False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=".embeddings-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return True


def execute_generation(
    arguments: argparse.Namespace, chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    api_key = os.environ.get(arguments.api_key_env, "").strip()
    if not api_key:
        raise ValueError(
            f"Set {arguments.api_key_env} before using --execute. "
            "Do not place the real key in source code."
        )

    payload = build_request_payload(chunks, arguments.model)
    response = request_embeddings(payload, api_key, arguments.timeout)
    embeddings = validate_embeddings(response, len(chunks))
    records = create_embedding_records(
        chunks, embeddings, arguments.model, response.get("model")
    )
    output_bytes = serialize_jsonl(records)
    output_hash = hashlib.sha256(output_bytes).hexdigest()

    output_directory = arguments.output_dir.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / (
        f"embeddings__{safe_model_name(arguments.model)}__"
        f"{output_hash[:12]}.jsonl"
    )
    created = write_once(target, output_bytes)

    return {
        "mode": "execute",
        "input": str(arguments.input.expanduser().resolve()),
        "output": str(target),
        "model": arguments.model,
        "chunk_count": len(chunks),
        "embedding_count": len(embeddings),
        "dimensions": len(embeddings[0]),
        "sha256": output_hash,
        "created": created,
    }


def generate_mock_examples(
    arguments: argparse.Namespace, chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    embeddings = [create_mock_embedding(chunk["text"]) for chunk in chunks]
    records = create_embedding_records(chunks, embeddings, MOCK_MODEL, MOCK_MODEL)
    for record in records:
        record["isMock"] = True
        record["usableForSearch"] = False
        record["warning"] = "Example vector only; replace with real model output."

    output_bytes = serialize_jsonl(records)
    output_hash = hashlib.sha256(output_bytes).hexdigest()
    output_directory = arguments.output_dir.expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / f"MOCK_EXAMPLE__{output_hash[:12]}.jsonl"
    created = write_once(target, output_bytes)

    return {
        "mode": "mock-example",
        "network_request_sent": False,
        "output": str(target),
        "model": MOCK_MODEL,
        "chunk_count": len(chunks),
        "embedding_count": len(embeddings),
        "dimensions": MOCK_DIMENSIONS,
        "usable_for_search": False,
        "created": created,
    }


def dry_run_summary(
    arguments: argparse.Namespace, chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    payload = build_request_payload(chunks, arguments.model)
    return {
        "mode": "dry-run",
        "network_request_sent": False,
        "endpoint": OPENROUTER_EMBEDDINGS_URL,
        "model": arguments.model,
        "chunk_count": len(chunks),
        "input_type": payload["input_type"],
        "api_key_environment_variable": arguments.api_key_env,
        "example_key_value": "replace_with_your_openrouter_api_key",
        "execute_command": (
            f'python "{Path(__file__).name}" "{arguments.input}" --execute'
        ),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate OpenRouter embeddings for prepared JSONL chunks."
    )
    parser.add_argument("input", type=Path, help="Path to step-6 chunk JSONL.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenRouter embedding model (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIRECTORY}).",
    )
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENVIRONMENT_VARIABLE,
        help=(
            "Environment-variable name that contains the API key "
            f"(default: {DEFAULT_API_KEY_ENVIRONMENT_VARIABLE})."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send the API request. Without this flag, only validate and preview.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Write deterministic example vectors without making a network request.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    try:
        if arguments.execute and arguments.mock:
            raise ValueError("Choose either --execute or --mock, not both.")
        chunks = load_chunks(arguments.input)
        if arguments.execute:
            result = execute_generation(arguments, chunks)
        elif arguments.mock:
            result = generate_mock_examples(arguments, chunks)
        else:
            result = dry_run_summary(arguments, chunks)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
