"""Step 1: preserve any source artifact and create a provenance manifest."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_core import (
    DATA_DIRECTORY,
    PIPELINE_VERSION,
    managed_relative,
    safe_slug,
    sha256_bytes,
    write_json,
    write_once,
)


DEFAULT_MANIFEST_DIRECTORY = DATA_DIRECTORY / "01_manifests"
DEFAULT_SOURCE_DIRECTORY = DATA_DIRECTORY / "01_sources"
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def infer_source_type(source: Path, source_url: str | None) -> str:
    suffix = source.suffix.lower()
    if suffix in {".htm", ".html"}:
        return "webpage"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx", ".odt", ".rtf"}:
        return "office_document"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "image"
    if source_url:
        return "derived_web_text" if suffix == ".txt" else "web_resource"
    return "text_document" if suffix in {".txt", ".md"} else "file"


def ingest_source(arguments: argparse.Namespace) -> tuple[dict[str, Any], Path, bool]:
    source = arguments.input.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    content = source.read_bytes()
    if not content:
        raise ValueError("Source file is empty.")

    digest = sha256_bytes(content)
    title = arguments.title or source.stem
    requested_document_id = getattr(arguments, "document_id", None)
    if requested_document_id and not DOCUMENT_ID_PATTERN.fullmatch(requested_document_id):
        raise ValueError("--document-id may contain only letters, numbers, dots, underscores, and hyphens.")
    document_id = requested_document_id or f"{safe_slug(title)}-{digest[:12]}"
    source_type = arguments.source_type or infer_source_type(source, arguments.source_url)
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"

    source_directory = arguments.source_dir.expanduser().resolve() / document_id / digest[:12]
    preserved_source = source_directory / f"original{source.suffix.lower() or '.bin'}"
    source_created = write_once(preserved_source, content)

    manifest_path = (
        arguments.manifest_dir.expanduser().resolve() / f"{document_id}__{digest[:12]}.json"
    )
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("source", {}).get("sha256") != digest:
            raise RuntimeError(f"Existing manifest has a different source hash: {manifest_path}")
        return existing, manifest_path, False

    retrieved_at = arguments.retrieved_at or datetime.now(timezone.utc).astimezone().isoformat()
    manifest = {
        "schemaVersion": "2.0",
        "pipelineVersion": PIPELINE_VERSION,
        "documentId": document_id,
        "title": title,
        "documentType": arguments.document_type or "unknown",
        "language": arguments.language,
        "publisher": arguments.publisher,
        "publishedDate": arguments.published_date,
        "retrievedAt": retrieved_at,
        "source": {
            "sourceType": source_type,
            "sourceStatus": getattr(arguments, "source_status", None),
            "sourceUrl": arguments.source_url,
            "originalFilename": source.name,
            "snapshotPath": managed_relative(preserved_source),
            "mediaType": media_type,
            "bytes": len(content),
            "sha256": digest,
        },
    }
    write_json(manifest_path, manifest)
    return manifest, manifest_path, source_created


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preserve a source artifact and create its manifest.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--document-id")
    parser.add_argument("--source-url")
    parser.add_argument("--source-type")
    parser.add_argument("--document-type")
    parser.add_argument("--publisher")
    parser.add_argument("--published-date")
    parser.add_argument("--retrieved-at")
    parser.add_argument("--source-status")
    parser.add_argument("--language", default="ro")
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIRECTORY)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        manifest, manifest_path, source_created = ingest_source(arguments)
    except (FileNotFoundError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "documentId": manifest["documentId"],
        "manifest": str(manifest_path),
        "snapshot": str((Path(__file__).resolve().parent / manifest["source"]["snapshotPath"]).resolve()),
        "sha256": manifest["source"]["sha256"],
        "sourceCreated": source_created,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
