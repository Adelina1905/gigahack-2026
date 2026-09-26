"""Step 5: validate schema, source integrity, passage citations, and readiness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pipeline_core import (
    DATA_DIRECTORY,
    MANAGE_DATA_DIRECTORY,
    read_json,
    resolve_managed_path,
    sha256_bytes,
    split_text_blocks,
    unique_preserving_order,
    write_versioned_json,
)


DEFAULT_OUTPUT_DIRECTORY = DATA_DIRECTORY / "05_validated"
DOCUMENT_SCHEMA = MANAGE_DATA_DIRECTORY / "schemas" / "document.schema.json"


def validate_schema(document: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ImportError as error:
        raise RuntimeError("Schema validation requires jsonschema. Install requirements.txt.") from error
    schema = read_json(DOCUMENT_SCHEMA)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        messages = [f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]
        raise ValueError("Document schema validation failed: " + "; ".join(messages))


def valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_source(document: dict[str, Any]) -> tuple[list[str], Path, list[str]]:
    data_issues: list[str] = []
    citation_issues: list[str] = []
    source = document["source"]
    source_path = resolve_managed_path(source["snapshotPath"])
    if not source_path.is_file():
        citation_issues.append("SOURCE_SNAPSHOT_MISSING")
    else:
        actual_hash = sha256_bytes(source_path.read_bytes())
        if actual_hash != source.get("sha256"):
            citation_issues.append("SOURCE_HASH_MISMATCH")
    if not valid_url(source.get("sourceUrl")):
        citation_issues.append("SOURCE_URL_MISSING_OR_INVALID")
    if source.get("sourceType") == "derived_web_text":
        citation_issues.append("RAW_WEBPAGE_SNAPSHOT_MISSING")
    if document.get("extraction", {}).get("requiresOcr"):
        data_issues.append("OCR_REQUIRED")
    if document.get("documentType") == "webpage_article":
        try:
            date.fromisoformat(document.get("publishedDate"))
        except (TypeError, ValueError):
            data_issues.append("PUBLICATION_DATE_MISSING_OR_INVALID")
    return data_issues, source_path, citation_issues


def validate_line_citation(passage: dict[str, Any], source_lines: list[str]) -> list[str]:
    provenance = passage.get("provenance", {})
    if provenance.get("kind") != "source_lines":
        return [] if provenance.get("kind") in {"pdf_page", "html_extraction"} else ["CITATION_LOCATOR_INVALID"]
    start = provenance.get("startLine")
    end = provenance.get("endLine")
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        return ["SOURCE_LINE_RANGE_INVALID"]
    if end > len(source_lines):
        return ["SOURCE_LINE_RANGE_OUT_OF_BOUNDS"]
    actual = "\n".join(source_lines[start - 1 : end]).strip()
    return [] if actual == passage.get("citationText") else ["CITATION_TEXT_SOURCE_MISMATCH"]


def validate_api_citation(
    passage: dict[str, Any], api_document: dict[str, Any]
) -> list[str]:
    provenance = passage.get("provenance", {})
    if provenance.get("kind") == "api_metadata":
        field = provenance.get("field")
        if field != "title":
            return ["API_METADATA_LOCATOR_INVALID"]
        return (
            []
            if api_document.get(field) == passage.get("quote", passage.get("citationText"))
            else ["CITATION_TEXT_SOURCE_MISMATCH"]
        )
    if provenance.get("kind") == "scraper_text":
        text = api_document.get("text")
        start = provenance.get("startLine")
        end = provenance.get("endLine")
        if (
            not isinstance(text, str)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 1
            or end < start
        ):
            return ["SCRAPER_TEXT_LOCATOR_INVALID"]
        lines = text.splitlines()
        if end > len(lines):
            return ["SCRAPER_TEXT_RANGE_OUT_OF_BOUNDS"]
        expected = "\n".join(lines[start - 1 : end]).strip()
        return [] if expected == passage.get("citationText") else ["CITATION_TEXT_SOURCE_MISMATCH"]
    if provenance.get("kind") not in {"api_page", "scraper_page"}:
        return ["CITATION_LOCATOR_INVALID"]
    page_index = provenance.get("pageIndex")
    block_index = provenance.get("blockIndex")
    pages = api_document.get("pages")
    if (
        not isinstance(pages, list)
        or not isinstance(page_index, int)
        or page_index < 0
        or page_index >= len(pages)
        or not isinstance(block_index, int)
        or block_index < 1
    ):
        return ["API_PAGE_LOCATOR_INVALID"]
    page = pages[page_index]
    if not isinstance(page, dict) or not isinstance(page.get("text"), str):
        return ["API_PAGE_TEXT_UNAVAILABLE"]
    blocks = split_text_blocks(page["text"])
    if block_index > len(blocks):
        return ["API_BLOCK_RANGE_OUT_OF_BOUNDS"]
    expected = blocks[block_index - 1]["citationText"]
    return [] if expected == passage.get("citationText") else ["CITATION_TEXT_SOURCE_MISMATCH"]


def validate_document(input_path: Path) -> dict[str, Any]:
    document = read_json(input_path)
    validate_schema(document)
    passages = document["passages"]
    source = document["source"]
    document_data_issues, source_path, document_citation_issues = validate_source(document)
    source_lines: list[str] = []
    api_document: dict[str, Any] | None = None
    if source_path.is_file() and source_path.suffix.lower() in {".txt", ".md", ".html", ".htm"}:
        try:
            source_lines = source_path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            document_citation_issues.append("SOURCE_TEXT_ENCODING_INVALID")
    elif source_path.is_file() and source.get("sourceType") in {
        "municipal_corpus_api", "chisinau_scraper_snapshot"
    }:
        try:
            api_document = read_json(source_path)
        except (OSError, ValueError):
            document_citation_issues.append("API_SOURCE_JSON_INVALID")
    title_citation = document.get("titleCitation")
    if title_citation is not None:
        if not isinstance(title_citation, dict) or api_document is None:
            document_citation_issues.append("TITLE_CITATION_INVALID")
        else:
            document_citation_issues.extend(validate_api_citation(title_citation, api_document))

    passage_ids: set[str] = set()
    ready_passages = 0
    for passage in passages:
        data_issues = list(passage.get("warnings", []))
        citation_issues: list[str] = []
        passage_id = passage["passageId"]
        if passage_id in passage_ids:
            data_issues.append("DUPLICATE_PASSAGE_ID")
        passage_ids.add(passage_id)
        if source_lines:
            citation_issues.extend(validate_line_citation(passage, source_lines))
        elif api_document is not None:
            citation_issues.extend(validate_api_citation(passage, api_document))
        elif passage.get("provenance", {}).get("kind") not in {"pdf_page", "html_extraction"}:
            citation_issues.append("CITATION_SOURCE_UNAVAILABLE")
        if not passage.get("citationText", "").strip():
            citation_issues.append("CITATION_TEXT_MISSING")
        data_status = "READY" if not data_issues else "NEEDS_REVIEW"
        citation_status = "READY" if not citation_issues and not document_citation_issues else "NEEDS_REVIEW"
        overall_status = "READY" if data_status == citation_status == "READY" else "NEEDS_REVIEW"
        passage["validation"] = {
            "dataStatus": data_status,
            "dataIssues": unique_preserving_order(data_issues),
            "citationStatus": citation_status,
            "citationIssues": unique_preserving_order(citation_issues + document_citation_issues),
            "overallStatus": overall_status,
        }
        ready_passages += overall_status == "READY"

    data_status = "READY" if passages and not document_data_issues else "NEEDS_REVIEW"
    citation_status = "READY" if passages and not document_citation_issues else "NEEDS_REVIEW"
    overall_status = "READY" if data_status == citation_status == "READY" and ready_passages == len(passages) else "NEEDS_REVIEW"
    # v3 quarantines bad passages without suppressing clean passages. Only broken
    # source identity/provenance or an unreadable document blocks the document.
    blocking_codes = {
        "SOURCE_SNAPSHOT_MISSING", "SOURCE_HASH_MISMATCH", "SOURCE_URL_MISSING_OR_INVALID",
        "RAW_WEBPAGE_SNAPSHOT_MISSING", "SOURCE_TEXT_ENCODING_INVALID", "API_SOURCE_JSON_INVALID",
        "OCR_REQUIRED",
    }
    blocking_document_issues = blocking_codes.intersection(document_data_issues + document_citation_issues)
    indexing_decision = "PRODUCTION" if ready_passages > 0 and not blocking_document_issues else "REVIEW"
    document["schemaVersion"] = "2.2"
    document["pipelineStage"] = "validated"
    document["validation"] = {
        "dataStatus": data_status,
        "dataIssues": unique_preserving_order(document_data_issues),
        "citationStatus": citation_status,
        "citationIssues": unique_preserving_order(document_citation_issues),
        "overallStatus": overall_status,
        "indexingDecision": indexing_decision,
    }
    document["qualityReport"] = {
        "totalPassages": len(passages),
        "readyPassages": ready_passages,
        "reviewPassages": len(passages) - ready_passages,
        "factCount": len(document.get("facts", [])),
    }
    return document


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a municipal document and its citations.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        document = validate_document(arguments.input)
        target, digest, created = write_versioned_json(arguments.output_dir.expanduser().resolve(), document["documentId"], "validated", document)
    except (FileNotFoundError, KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"documentId": document["documentId"], "output": str(target), "validation": document["validation"], "qualityReport": document["qualityReport"], "sha256": digest, "created": created}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
