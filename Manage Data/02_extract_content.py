"""Step 2: extract citation-preserving blocks from a source manifest."""

from __future__ import annotations

import argparse
import codecs
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_core import (
    DATA_V2_DIRECTORY,
    is_heading,
    parse_metadata_preface,
    read_json,
    resolve_managed_path,
    sha256_text,
    split_text_blocks,
    stable_id,
    write_versioned_json,
)


DEFAULT_OUTPUT_DIRECTORY = DATA_V2_DIRECTORY / "02_extracted"


def decode_text(content: bytes) -> str:
    if content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        decoder = "utf-16"
    elif content.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        decoder = "utf-32"
    else:
        decoder = "utf-8-sig"
    try:
        return content.decode(decoder)
    except UnicodeDecodeError as error:
        raise ValueError("Text source is not valid Unicode text.") from error


def extract_text_source(manifest: dict[str, Any], source_path: Path) -> dict[str, Any]:
    original_text = decode_text(source_path.read_bytes())
    preface_metadata, content_text, first_line = parse_metadata_preface(original_text)
    if not content_text.strip():
        content_text = original_text
        first_line = 1

    blocks = split_text_blocks(content_text, first_line_number=first_line)
    output_blocks: list[dict[str, Any]] = []
    for order, block in enumerate(blocks, start=1):
        citation_text = block["citationText"]
        stripped_lines = [line.strip() for line in citation_text.splitlines() if line.strip()]
        if len(stripped_lines) == 1 and is_heading(stripped_lines[0]):
            block_type = "heading"
        elif stripped_lines and all(line.startswith(("- ", "• ", "* ")) for line in stripped_lines):
            block_type = "list"
        elif any(line.startswith("Locația:") for line in stripped_lines) and any(
            line.startswith("Perioada:") for line in stripped_lines
        ):
            block_type = "municipal_event"
        else:
            block_type = "paragraph"
        output_blocks.append({
            "blockId": stable_id("block", manifest["documentId"], str(order), citation_text),
            "order": order,
            "type": block_type,
            "citationText": citation_text,
            "searchText": block["searchText"],
            "contentHash": sha256_text(citation_text),
            "provenance": {
                "kind": "source_lines",
                "startLine": block["startLine"],
                "endLine": block["endLine"],
            },
        })

    return {
        "schemaVersion": "2.0",
        "pipelineStage": "extracted",
        "documentId": manifest["documentId"],
        "manifest": manifest,
        "extraction": {
            "engine": "native_text",
            "status": "READY",
            "requiresOcr": False,
            "warnings": ["DERIVED_WEB_TEXT"]
            if manifest["source"]["sourceType"] == "derived_web_text"
            else [],
        },
        "extractedMetadata": preface_metadata,
        "blocks": output_blocks,
    }


def extract_pdf_source(manifest: dict[str, Any], source_path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("PDF extraction requires pypdf. Install requirements.txt.") from error

    reader = PdfReader(source_path)
    blocks: list[dict[str, Any]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        for page_order, block in enumerate(split_text_blocks(text), start=1):
            citation_text = block["citationText"]
            blocks.append({
                "blockId": stable_id(
                    "block", manifest["documentId"], str(page_number), str(page_order), citation_text
                ),
                "order": len(blocks) + 1,
                "type": "paragraph",
                "citationText": citation_text,
                "searchText": block["searchText"],
                "contentHash": sha256_text(citation_text),
                "provenance": {"kind": "pdf_page", "page": page_number},
            })

    requires_ocr = not blocks
    return {
        "schemaVersion": "2.0",
        "pipelineStage": "extracted",
        "documentId": manifest["documentId"],
        "manifest": manifest,
        "extraction": {
            "engine": "pypdf",
            "status": "OCR_REQUIRED" if requires_ocr else "READY",
            "requiresOcr": requires_ocr,
            "pageCount": len(reader.pages),
            "warnings": ["IMAGE_ONLY_PDF"] if requires_ocr else [],
        },
        "extractedMetadata": {},
        "blocks": blocks,
    }


def extract_html_source(manifest: dict[str, Any], source_path: Path) -> dict[str, Any]:
    try:
        import trafilatura
    except ImportError as error:
        raise RuntimeError("HTML extraction requires trafilatura. Install requirements.txt.") from error

    extracted_json = trafilatura.extract(
        source_path.read_bytes(),
        url=manifest.get("source", {}).get("sourceUrl"),
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        include_images=True,
        include_links=True,
        deduplicate=True,
    )
    if not extracted_json:
        raise ValueError("Trafilatura could not identify article content in the HTML source.")
    extracted_value = json.loads(extracted_json)
    text = extracted_value.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("HTML extraction returned no main text.")

    blocks: list[dict[str, Any]] = []
    for order, block in enumerate(split_text_blocks(text), start=1):
        citation_text = block["citationText"]
        blocks.append({
            "blockId": stable_id("block", manifest["documentId"], str(order), citation_text),
            "order": order,
            "type": "heading"
            if len(citation_text.splitlines()) == 1 and is_heading(citation_text)
            else "paragraph",
            "citationText": citation_text,
            "searchText": block["searchText"],
            "contentHash": sha256_text(citation_text),
            "provenance": {
                "kind": "html_extraction",
                "extractor": "trafilatura",
                "order": order,
            },
        })

    metadata = {
        "Title": extracted_value.get("title") or "",
        "Publication date": extracted_value.get("date") or "",
        "Publisher": extracted_value.get("sitename") or "",
        "Source URL": extracted_value.get("url")
        or manifest.get("source", {}).get("sourceUrl")
        or "",
        "Main image URL": extracted_value.get("image") or "",
    }
    return {
        "schemaVersion": "2.0",
        "pipelineStage": "extracted",
        "documentId": manifest["documentId"],
        "manifest": manifest,
        "extraction": {
            "engine": "trafilatura",
            "status": "READY",
            "requiresOcr": False,
            "warnings": [],
        },
        "extractedMetadata": metadata,
        "blocks": blocks,
    }


def extract_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    source_path = resolve_managed_path(manifest["source"]["snapshotPath"])
    if not source_path.is_file():
        raise FileNotFoundError(f"Preserved source is missing: {source_path}")
    media_type = manifest["source"].get("mediaType", "")
    suffix = source_path.suffix.lower()
    if media_type == "application/pdf" or suffix == ".pdf":
        return extract_pdf_source(manifest, source_path)
    if media_type == "text/html" or suffix in {".html", ".htm"}:
        return extract_html_source(manifest, source_path)
    if media_type.startswith("text/") or suffix in {".txt", ".md", ".csv"}:
        return extract_text_source(manifest, source_path)
    raise ValueError(
        f"No active extractor for {media_type or suffix}. Use Docling to export this source "
        "to structured JSON or text, then ingest that export."
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract source content into provenance blocks.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        document = extract_manifest(arguments.manifest)
        target, digest, created = write_versioned_json(
            arguments.output_dir.expanduser().resolve(),
            document["documentId"],
            "extracted",
            document,
        )
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "documentId": document["documentId"],
        "output": str(target),
        "extractionStatus": document["extraction"]["status"],
        "blockCount": len(document["blocks"]),
        "sha256": digest,
        "created": created,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
