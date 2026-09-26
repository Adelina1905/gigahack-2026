"""Step 6: create exact, passage-level evidence units (schema v3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_core import (
    DATA_DIRECTORY,
    MANAGE_DATA_DIRECTORY,
    estimate_tokens,
    read_json,
    sha256_bytes,
    sha256_text,
    stable_id,
    write_once,
)
from municipal_rag.evidence import build_evidence


DEFAULT_OUTPUT_DIRECTORY = DATA_DIRECTORY / "06_chunks"
CHUNK_SCHEMA = MANAGE_DATA_DIRECTORY / "schemas" / "chunk.schema.json"


def validate_chunk_schema(chunk: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as error:
        raise RuntimeError("Chunk validation requires jsonschema. Install requirements.txt.") from error
    schema = read_json(CHUNK_SCHEMA)
    jsonschema.Draft202012Validator(schema).validate(chunk)


def can_merge(current: list[dict[str, Any]], candidate: dict[str, Any], max_tokens: int) -> bool:
    if not current:
        return True
    if current[-1].get("headingPath") != candidate.get("headingPath"):
        return False
    if current[-1].get("type") == "municipal_event" or candidate.get("type") == "municipal_event":
        return False
    combined = "\n\n".join(item["searchText"] for item in current + [candidate])
    return estimate_tokens(combined) <= max_tokens


def group_passages(passages: list[dict[str, Any]], max_tokens: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for passage in passages:
        if current and not can_merge(current, passage, max_tokens):
            groups.append(current)
            current = []
        current.append(passage)
    if current:
        groups.append(current)
    return groups


def chunk_status(document: dict[str, Any], passages: list[dict[str, Any]]) -> str:
    if document.get("validation", {}).get("dataStatus") != "READY":
        return "NEEDS_REVIEW"
    if any(passage.get("validation", {}).get("dataStatus") != "READY" for passage in passages):
        return "NEEDS_REVIEW"
    if document.get("validation", {}).get("citationStatus") != "READY":
        return "CITATION_PENDING"
    if any(passage.get("validation", {}).get("citationStatus") != "READY" for passage in passages):
        return "CITATION_PENDING"
    return "READY"


def create_chunk(document: dict[str, Any], passages: list[dict[str, Any]], sequence: int) -> dict[str, Any]:
    body = "\n\n".join(passage["searchText"] for passage in passages)
    heading_path = passages[0].get("headingPath", [])
    context_parts = [document["title"]]
    if document.get("publishedDate"):
        context_parts.append(f"Publicat: {document['publishedDate']}")
    context_parts.extend(heading_path)
    retrieval_text = " | ".join(context_parts) + "\n\n" + body
    citation_text = "\n\n".join(passage["citationText"] for passage in passages)
    passage_ids = [passage["passageId"] for passage in passages]
    chunk_id = stable_id("chunk", document["documentId"], str(sequence), *passage_ids)
    citations: list[dict[str, Any]] = []
    title_citation = document.get("titleCitation")
    if isinstance(title_citation, dict):
        citations.append({
            "passageId": title_citation["passageId"],
            "sourceUrl": document["source"].get("sourceUrl"),
            "sourceFile": document["source"].get("originalFilename"),
            "locator": title_citation["provenance"],
            "quote": title_citation["quote"],
        })
    citations.extend([
        {
            "passageId": passage["passageId"],
            "sourceUrl": document["source"].get("sourceUrl"),
            "sourceFile": document["source"].get("originalFilename"),
            "locator": passage["provenance"],
            "quote": passage["citationText"],
        }
        for passage in passages
    ])
    status = chunk_status(document, passages)
    chunk = {
        "chunkId": chunk_id,
        "documentId": document["documentId"],
        "documentType": document["documentType"],
        "language": document["language"],
        "text": retrieval_text,
        "citationText": citation_text,
        "textSha256": sha256_text(retrieval_text),
        "tokenCountEstimate": estimate_tokens(retrieval_text),
        "passageIds": passage_ids,
        "citations": citations,
        "indexingStatus": status,
        "targetCollection": "production" if status == "READY" else "review",
        "metadata": {
            "title": document["title"],
            "publisher": document.get("publisher"),
            "publishedDate": document.get("publishedDate"),
            "statisticsAsOf": document.get("temporalContext", {}).get("statisticsAsOf"),
            "headingPath": heading_path,
            "sourceUrl": document["source"].get("sourceUrl"),
            "source": document.get("sourceMetadata", {}).get("source"),
            "category": document.get("sourceMetadata", {}).get("category"),
            "district": document.get("sourceMetadata", {}).get("district"),
            "tier": document.get("sourceMetadata", {}).get("tier"),
        },
    }
    validate_chunk_schema(chunk)
    return chunk


def create_chunks(input_path: Path, max_tokens: int, ready_only: bool) -> list[dict[str, Any]]:
    if max_tokens < 64:
        raise ValueError("--max-tokens must be at least 64.")
    document = read_json(input_path)
    if document.get("pipelineStage") != "validated":
        raise ValueError("Step 6 requires a step-5 validated document.")
    passages = document.get("passages")
    if not isinstance(passages, list) or not passages:
        raise ValueError("Validated document contains no passages.")
    if max_tokens > 420:
        max_tokens = 420
    chunks = build_evidence(document, hard_max_tokens=max_tokens)
    for chunk in chunks:
        validate_chunk_schema(chunk)
    # Quarantined evidence is reported by validation but is never written into
    # the production chunk artifact, irrespective of the legacy flag.
    return [chunk for chunk in chunks if chunk["indexingStatus"] == "READY"]


def serialize_jsonl(chunks: list[dict[str, Any]]) -> bytes:
    if not chunks:
        return b""
    return ("\n".join(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) for chunk in chunks) + "\n").encode("utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create generic, citation-ready retrieval chunks.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--max-tokens", type=int, default=420)
    parser.add_argument("--ready-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        chunks = create_chunks(arguments.input, arguments.max_tokens, arguments.ready_only)
        output_bytes = serialize_jsonl(chunks)
        digest = sha256_bytes(output_bytes)
        document = read_json(arguments.input)
        target = arguments.output_dir.expanduser().resolve() / f"{document['documentId']}__chunks__{digest[:12]}.jsonl"
        created = write_once(target, output_bytes)
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk["indexingStatus"]] = counts.get(chunk["indexingStatus"], 0) + 1
    print(json.dumps({"documentId": document["documentId"], "output": str(target), "chunkCount": len(chunks), "statusCounts": counts, "maxTokens": arguments.max_tokens, "sha256": digest, "created": created}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
