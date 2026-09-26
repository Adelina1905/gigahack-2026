"""Shared primitives for the version-2 municipal document pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterable


PIPELINE_VERSION = "2.0"
MANAGE_DATA_DIRECTORY = Path(__file__).resolve().parent
DATA_V2_DIRECTORY = MANAGE_DATA_DIRECTORY / "data" / "v2"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def safe_slug(value: str, fallback: str = "document") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-_.").lower()
    return slug or fallback


def stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    digest = sha256_text("\x1f".join(parts))[:length]
    return f"{prefix}-{digest}"


def managed_relative(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(MANAGE_DATA_DIRECTORY).as_posix()
    except ValueError:
        return str(resolved)


def resolve_managed_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (MANAGE_DATA_DIRECTORY / path).resolve()


def write_once(target: Path, content: bytes) -> bool:
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != content:
            raise RuntimeError(f"Existing output has unexpected content: {target}")
        return False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.stem}-",
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


def write_json(target: Path, value: Any) -> bool:
    content = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return write_once(target, content)


def write_versioned_json(
    directory: Path, stem: str, stage: str, value: Any
) -> tuple[Path, str, bool]:
    content = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    digest = sha256_bytes(content)
    target = directory / f"{safe_slug(stem)}__{stage}__{digest[:12]}.json"
    return target, digest, write_once(target, content)


def read_json(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"JSON input does not exist: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError(f"JSON input must be UTF-8: {source}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {source}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must contain an object: {source}")
    return value


def normalize_search_text(text: str) -> str:
    """Normalize retrieval text without changing the citation representation."""
    value = unicodedata.normalize("NFC", text)
    value = value.replace("\u00a0", " ").replace("\u202f", " ")
    normalized_lines = [re.sub(r"[\t ]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in normalized_lines if line).strip()


def is_heading(text: str) -> bool:
    value = text.strip()
    if not value or "\n" in value or len(value) > 160:
        return False
    if value in {"SOURCE METADATA", "ARTICLE CONTENT", "SUBSTANTIVE IMAGE TEXT"}:
        return True
    letters = [character for character in value if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def split_text_blocks(text: str, first_line_number: int = 1) -> list[dict[str, Any]]:
    """Split text on blank lines while retaining one-based source line locators."""
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    current: list[str] = []
    start: int | None = None

    def flush(end_index: int) -> None:
        nonlocal current, start
        if not current or start is None:
            return
        citation_text = "\n".join(current).strip()
        if citation_text:
            blocks.append(
                {
                    "citationText": citation_text,
                    "searchText": normalize_search_text(citation_text),
                    "startLine": first_line_number + start,
                    "endLine": first_line_number + end_index,
                }
            )
        current = []
        start = None

    for index, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = index
            current.append(line.rstrip())
        else:
            flush(index - 1)
    flush(len(lines) - 1)
    return blocks


def parse_metadata_preface(text: str) -> tuple[dict[str, str], str, int]:
    """Read an optional human-readable SOURCE METADATA preface."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "SOURCE METADATA":
        return {}, text, 1

    metadata: dict[str, str] = {}
    content_start: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if stripped == "ARTICLE CONTENT":
            content_start = index
            break
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

    if content_start is None:
        return metadata, "", len(lines) + 1
    content = "\n".join(lines[content_start:])
    return metadata, content, content_start + 1


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-independent estimate, replaced at embedding time."""
    words_and_punctuation = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return max(1, int(len(words_and_punctuation) * 1.25 + 0.5))


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
