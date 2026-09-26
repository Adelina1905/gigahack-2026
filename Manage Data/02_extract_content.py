"""Step 2: extract citation-preserving blocks from a source manifest."""

from __future__ import annotations

import argparse
import codecs
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_core import (
    DATA_DIRECTORY,
    is_heading,
    parse_metadata_preface,
    read_json,
    resolve_managed_path,
    sha256_text,
    split_text_blocks,
    stable_id,
    write_versioned_json,
)


DEFAULT_OUTPUT_DIRECTORY = DATA_DIRECTORY / "02_extracted"


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


def api_block_type(citation_text: str) -> str:
    stripped = citation_text.strip()
    lines = stripped.splitlines()
    if len(lines) == 1 and stripped.startswith("#") and stripped.lstrip("#").lstrip():
        return "heading"
    if len(lines) == 1 and is_heading(stripped):
        return "heading"
    return "paragraph"


def extract_api_document(manifest: dict[str, Any], source_path: Path) -> dict[str, Any]:
    """Adapt a municipal corpus API response without losing page citations."""
    api_document = read_json(source_path)
    api_id = api_document.get("id")
    if not isinstance(api_id, str) or not api_id:
        raise ValueError("Corpus API JSON has no document id.")
    if api_id != manifest.get("documentId"):
        raise ValueError(
            f"Corpus API id {api_id!r} does not match manifest id {manifest.get('documentId')!r}."
        )
    pages = api_document.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Corpus API JSON has no pages[] array.")

    blocks: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("Every corpus API page must be an object.")
        text = page.get("text")
        if text is None:
            continue
        if not isinstance(text, str):
            raise ValueError("Corpus API page text must be a string or null.")
        for block_index, block in enumerate(split_text_blocks(text), start=1):
            citation_text = block["citationText"]
            blocks.append({
                "blockId": stable_id(
                    "block",
                    manifest["documentId"],
                    str(page_index),
                    str(block_index),
                    citation_text,
                ),
                "order": len(blocks) + 1,
                "type": api_block_type(citation_text),
                "citationText": citation_text,
                "searchText": block["searchText"],
                "contentHash": sha256_text(citation_text),
                "provenance": {
                    "kind": "api_page",
                    "page": page.get("page"),
                    "pageIndex": page_index,
                    "blockIndex": block_index,
                },
            })

    pending_pages = api_document.get("ocr_pending_pages")
    if pending_pages is None:
        pending_pages = []
    if not isinstance(pending_pages, list):
        raise ValueError("Corpus API ocr_pending_pages must be an array.")
    api_status = api_document.get("status")
    requires_ocr = bool(pending_pages) or api_status in {"needs_ocr", "ocr_partial"}
    quality_flags = api_document.get("quality_flags") or []
    if not isinstance(quality_flags, list):
        raise ValueError("Corpus API quality_flags must be an array.")
    warnings = [str(flag) for flag in quality_flags]
    if pending_pages:
        warnings.append("OCR_PAGES_PENDING")

    title = api_document.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Corpus API JSON has no title.")
    source_name = api_document.get("source")
    canonical_url = api_document.get("canonical_url")
    return {
        "schemaVersion": "2.0",
        "pipelineStage": "extracted",
        "documentId": manifest["documentId"],
        "manifest": manifest,
        "extraction": {
            "engine": f"corpus_api:{api_document.get('extraction_method') or 'unknown'}",
            "status": "OCR_REQUIRED" if requires_ocr else ("READY" if blocks else "EMPTY"),
            "requiresOcr": requires_ocr,
            "warnings": warnings,
            "apiStatus": api_status,
            "pageCount": len(pages),
        },
        "extractedMetadata": {
            "Title": title.strip(),
            "Publication date": api_document.get("doc_date") or "",
            "Publisher": source_name if isinstance(source_name, str) else "",
            "Source URL": canonical_url if isinstance(canonical_url, str) else "",
            "Language": api_document.get("lang") or manifest.get("language") or "ro",
        },
        "sourceMetadata": {
            "apiDocumentId": api_id,
            "source": source_name,
            "category": api_document.get("category"),
            "district": api_document.get("district"),
            "tier": api_document.get("tier"),
            "curationReasons": api_document.get("curation_reasons") or [],
            "rawUrl": api_document.get("raw_url"),
            "contentType": api_document.get("content_type"),
            "apiUpdatedAt": api_document.get("updated_at"),
            "act": api_document.get("act"),
        },
        "blocks": blocks,
    }


def scraper_source_url(document: dict[str, Any]) -> str:
    urls = document.get("urls")
    if isinstance(urls, list):
        for item in urls:
            value = item.get("url") if isinstance(item, dict) else item
            if isinstance(value, str) and value.startswith(("https://", "http://")):
                return value
    return ""


def extract_scraper_document(
    manifest: dict[str, Any], source_path: Path, source_status: str | None = None
) -> dict[str, Any]:
    """Adapt extracted scraper JSON while retaining exact page/text locators."""
    document = read_json(source_path)
    sha1 = document.get("sha1")
    if not isinstance(sha1, str) or len(sha1) != 40:
        raise ValueError("Scraper JSON has no valid sha1.")

    blocks: list[dict[str, Any]] = []

    def append_blocks(text: str, provenance: dict[str, Any]) -> None:
        for block_index, block in enumerate(split_text_blocks(text), start=1):
            citation_text = block["citationText"]
            blocks.append({
                "blockId": stable_id(
                    "block", manifest["documentId"], str(len(blocks) + 1), citation_text
                ),
                "order": len(blocks) + 1,
                "type": api_block_type(citation_text),
                "citationText": citation_text,
                "searchText": block["searchText"],
                "contentHash": sha256_text(citation_text),
                "provenance": {**provenance, "blockIndex": block_index},
            })

    pages = document.get("pages")
    if pages is not None:
        if not isinstance(pages, list):
            raise ValueError("Scraper JSON pages must be an array.")
        for page_index, page in enumerate(pages):
            if not isinstance(page, dict):
                raise ValueError("Every scraper page must be an object.")
            text = page.get("text")
            if text is None:
                continue
            if not isinstance(text, str):
                raise ValueError("Scraper page text must be a string or null.")
            append_blocks(text, {
                "kind": "scraper_page",
                "page": page.get("page") or page_index + 1,
                "pageIndex": page_index,
                "ocr": bool(page.get("ocr")),
            })

    text = document.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise ValueError("Scraper JSON text must be a string.")
        for block in split_text_blocks(text):
            citation_text = block["citationText"]
            blocks.append({
                "blockId": stable_id(
                    "block", manifest["documentId"], str(len(blocks) + 1), citation_text
                ),
                "order": len(blocks) + 1,
                "type": api_block_type(citation_text),
                "citationText": citation_text,
                "searchText": block["searchText"],
                "contentHash": sha256_text(citation_text),
                "provenance": {
                    "kind": "scraper_text",
                    "startLine": block["startLine"],
                    "endLine": block["endLine"],
                },
            })

    pending_pages = document.get("needs_ocr_pages") or []
    if not isinstance(pending_pages, list):
        raise ValueError("Scraper JSON needs_ocr_pages must be an array.")
    quality_flags = document.get("quality_flags") or []
    if not isinstance(quality_flags, list):
        raise ValueError("Scraper JSON quality_flags must be an array.")
    warnings = [str(flag) for flag in quality_flags]
    extraction_status = source_status or manifest.get("source", {}).get("sourceStatus")
    if extraction_status in {"needs_ocr", "ocr_partial", "ocr_error"}:
        warnings.append("OCR_PAGES_PENDING")
    blocking_ocr_flags = {"low_ocr_conf", "ocr_truncated", "ocr_timeout"}
    if extraction_status is None:
        # In exports without manifest.sqlite, n_ocr_pages indicates that the
        # listed pages have already been processed rather than still pending.
        inferred_pending = bool(pending_pages) and not isinstance(
            document.get("n_ocr_pages"), int
        )
    else:
        inferred_pending = extraction_status in {"needs_ocr", "ocr_partial", "ocr_error"}
    requires_ocr = inferred_pending or bool(blocking_ocr_flags.intersection(warnings))
    status = "OCR_REQUIRED" if requires_ocr else ("READY" if blocks else "EMPTY")

    title = document.get("title") or manifest.get("title") or ""
    source_name = document.get("source")
    return {
        "schemaVersion": "2.0",
        "pipelineStage": "extracted",
        "documentId": manifest["documentId"],
        "manifest": manifest,
        "extraction": {
            "engine": f"chisinau_scraper:{document.get('method') or 'unknown'}",
            "status": status,
            "requiresOcr": requires_ocr,
            "warnings": list(dict.fromkeys(warnings)),
            "pageCount": len(pages) if isinstance(pages, list) else None,
            "sourceSha1": sha1,
            "sourceStatus": extraction_status,
        },
        "extractedMetadata": {
            "Title": str(title).strip(),
            "Publication date": document.get("doc_date") or "",
            "Publisher": source_name if isinstance(source_name, str) else "",
            "Source URL": scraper_source_url(document),
            "Language": document.get("lang") or manifest.get("language") or "ro",
        },
        "sourceMetadata": {
            "sourceSha1": sha1,
            "source": source_name,
            "category": document.get("category"),
            "district": document.get("district"),
            "contentType": document.get("content_type"),
            "extractedAt": document.get("extracted_at"),
            "actId": document.get("act_id"),
            "act": document.get("act"),
            "sourceUrls": document.get("urls") or [],
        },
        "blocks": blocks,
    }


def extract_manifest(
    manifest_path: Path, source_status: str | None = None
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    source_path = resolve_managed_path(manifest["source"]["snapshotPath"])
    if not source_path.is_file():
        raise FileNotFoundError(f"Preserved source is missing: {source_path}")
    media_type = manifest["source"].get("mediaType", "")
    suffix = source_path.suffix.lower()
    if manifest["source"].get("sourceType") == "municipal_corpus_api":
        return extract_api_document(manifest, source_path)
    if manifest["source"].get("sourceType") == "chisinau_scraper_snapshot":
        return extract_scraper_document(manifest, source_path, source_status)
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
    parser.add_argument("--source-status")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        document = extract_manifest(arguments.manifest, arguments.source_status)
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
