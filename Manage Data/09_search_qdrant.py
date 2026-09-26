"""Embed a Romanian query and search real vectors stored in Qdrant."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient


EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_MODEL = "qwen/qwen3-embedding-8b"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_PATH = Path(__file__).resolve().parent / "data" / "08_qdrant"
DEFAULT_COLLECTION = "municipal_evidence_current"


def read_api_key(variable_name: str) -> str:
    """Read a process variable, then the Windows user environment as fallback."""
    value = os.environ.get(variable_name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as environment_key:
            stored_value, _ = winreg.QueryValueEx(environment_key, variable_name)
        return stored_value.strip() if isinstance(stored_value, str) else ""
    except (FileNotFoundError, OSError):
        return ""


def embed_query(text: str, model: str, api_key: str, timeout: float) -> list[float]:
    request = urllib.request.Request(
        EMBEDDINGS_URL,
        data=json.dumps({
            "model": model,
            "input": text,
            "input_type": "search_query",
            "encoding_format": "float",
        }, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "gigahack-2026-municipal-data/2.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"OpenRouter returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach OpenRouter: {error.reason}") from error
    data = body.get("data") if isinstance(body, dict) else None
    vector = data[0].get("embedding") if isinstance(data, list) and len(data) == 1 else None
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("OpenRouter returned no query embedding.")
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector):
        raise RuntimeError("OpenRouter returned an invalid query embedding.")
    return [float(value) for value in vector]


def format_result(point: Any, rank: int) -> dict[str, Any]:
    payload = point.payload or {}
    return {
        "rank": rank,
        "score": round(float(point.score), 6),
        "chunkId": payload.get("chunkId"),
        "documentId": payload.get("documentId"),
        "title": (payload.get("metadata") or {}).get("title"),
        "text": payload.get("text"),
        "indexingStatus": payload.get("indexingStatus"),
        "citations": payload.get("citations") or [],
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Qdrant with a Romanian query.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--url", help="Qdrant server URL instead of local storage.")
    location.add_argument("--path", type=Path, help="Persistent local Qdrant directory.")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-api-key-env", default="QDRANT_API_KEY")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    try:
        if not arguments.text.strip():
            raise ValueError("--text cannot be empty.")
        if not 1 <= arguments.limit <= 20:
            raise ValueError("--limit must be between 1 and 20.")
        api_key = read_api_key(arguments.api_key_env)
        if not api_key:
            raise ValueError(f"Set {arguments.api_key_env} before searching.")
        vector = embed_query(arguments.text, arguments.model, api_key, arguments.timeout)
        if arguments.url:
            qdrant_api_key = read_api_key(arguments.qdrant_api_key_env) or None
            client = QdrantClient(url=arguments.url, api_key=qdrant_api_key, timeout=20)
            qdrant_location = arguments.url
        else:
            local_path = (arguments.path or DEFAULT_QDRANT_PATH).expanduser().resolve()
            client = QdrantClient(path=str(local_path))
            qdrant_location = str(local_path)
        collection = client.get_collection(arguments.collection)
        vector_config = collection.config.params.vectors
        dense_config = vector_config.get("dense") if isinstance(vector_config, dict) else vector_config
        if dense_config is None:
            raise ValueError("Collection has no dense vector.")
        if dense_config.size != len(vector):
            raise ValueError(
                f"Query has {len(vector)} dimensions but the collection requires {dense_config.size}."
            )
        response = client.query_points(
            collection_name=arguments.collection,
            query=vector,
            using="dense" if isinstance(vector_config, dict) else None,
            limit=arguments.limit,
            with_payload=True,
            with_vectors=False,
        )
        results = [format_result(point, rank) for rank, point in enumerate(response.points, start=1)]
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "collection": arguments.collection,
        "qdrantLocation": qdrant_location,
        "model": arguments.model,
        "queryLanguage": "ro",
        "query": arguments.text,
        "dimensions": len(vector),
        "resultCount": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
