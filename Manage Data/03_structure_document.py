"""Step 3: build a generic municipal document with stable cited passages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_core import DATA_V2_DIRECTORY, read_json, sha256_text, stable_id, write_versioned_json


DEFAULT_OUTPUT_DIRECTORY = DATA_V2_DIRECTORY / "03_structured"


def metadata_value(extracted: dict[str, Any], key: str) -> str | None:
    value = extracted.get("extractedMetadata", {}).get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def parse_event_attributes(text: str) -> dict[str, Any]:
    title_lines: list[str] = []
    location: str | None = None
    period: str | None = None
    extra_lines: list[str] = []
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        if line.startswith("Locația:"):
            location = line[len("Locația:") :].strip().rstrip(".") or None
        elif line.startswith("Perioada:"):
            period = line[len("Perioada:") :].strip().rstrip(".") or None
        elif location is None and period is None:
            title_lines.append(line)
        else:
            extra_lines.append(line)
    return {
        "title": " ".join(title_lines).rstrip(".") or None,
        "location": location,
        "periodRaw": period,
        "unrecognizedLines": extra_lines,
    }


def infer_document_type(manifest: dict[str, Any]) -> str:
    declared = manifest.get("documentType")
    if isinstance(declared, str) and declared != "unknown":
        return declared
    source_type = manifest.get("source", {}).get("sourceType")
    return {
        "derived_web_text": "webpage_article",
        "webpage": "webpage_article",
        "pdf": "administrative_document",
    }.get(source_type, "municipal_document")


def structure_document(input_path: Path) -> dict[str, Any]:
    extracted = read_json(input_path)
    manifest = extracted.get("manifest")
    blocks = extracted.get("blocks")
    if not isinstance(manifest, dict) or not isinstance(blocks, list):
        raise ValueError("Extracted input must contain manifest and blocks.")

    source = dict(manifest.get("source", {}))
    source["sourceUrl"] = source.get("sourceUrl") or metadata_value(extracted, "Source URL")
    title = metadata_value(extracted, "Title") or manifest.get("title")
    publisher = metadata_value(extracted, "Publisher") or manifest.get("publisher")
    published_date = metadata_value(extracted, "Publication date") or manifest.get("publishedDate")

    passages: list[dict[str, Any]] = []
    heading_path: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Every extracted block must be an object.")
        if block.get("type") == "heading":
            heading_path = [block["searchText"]]
            continue

        passage_id = stable_id(
            "passage",
            manifest["documentId"],
            block["blockId"],
            block["contentHash"],
        )
        passage: dict[str, Any] = {
            "passageId": passage_id,
            "order": len(passages) + 1,
            "type": block.get("type", "paragraph"),
            "headingPath": list(heading_path),
            "citationText": block["citationText"],
            "searchText": block["searchText"],
            "contentHash": block["contentHash"],
            "provenance": block["provenance"],
        }
        if block.get("type") == "municipal_event":
            passage["attributes"] = parse_event_attributes(block["citationText"])
        passages.append(passage)

    document = {
        "schemaVersion": "2.0",
        "pipelineStage": "structured",
        "documentId": manifest["documentId"],
        "documentType": infer_document_type(manifest),
        "title": title,
        "language": metadata_value(extracted, "Language") or manifest.get("language", "ro"),
        "publisher": publisher,
        "publishedDate": published_date,
        "retrievedAt": manifest.get("retrievedAt"),
        "source": source,
        "extraction": extracted.get("extraction", {}),
        "assets": [
            {
                "type": "image",
                "url": metadata_value(extracted, "Main image URL"),
            }
        ]
        if metadata_value(extracted, "Main image URL")
        else [],
        "passages": passages,
        "contentHash": sha256_text("\n\n".join(p["citationText"] for p in passages)),
    }
    return document


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a generic structured municipal document.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        document = structure_document(arguments.input)
        target, digest, created = write_versioned_json(
            arguments.output_dir.expanduser().resolve(),
            document["documentId"],
            "structured",
            document,
        )
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "documentId": document["documentId"],
        "documentType": document["documentType"],
        "output": str(target),
        "passageCount": len(document["passages"]),
        "sha256": digest,
        "created": created,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
