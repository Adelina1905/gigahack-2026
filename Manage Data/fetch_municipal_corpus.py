"""Resumably collect immutable document snapshots from the municipal corpus API.

The API is read in pages, but every document is validated and written separately.
Credentials are loaded from .env/environment variables and are never persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import time

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://scratch.faflist.solutions/api/v1"
DEFAULT_OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "Original Data" / "municipal_corpus"
DEFAULT_STATE_FILENAME = ".collector-state.json"

STATE_VERSION = 1
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class CollectionError(RuntimeError):
    """Raised when an API response cannot be collected safely."""


def load_local_env(env_path: Path) -> None:
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def read_environment_secret(variable_name: str) -> str:
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


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        temporary_path.replace(target)

    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": STATE_VERSION}

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionError(f"Cannot read collector state {path}: {error}") from error

    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        raise CollectionError(f"Unsupported collector state in {path}")

    return value


def write_state(path: Path, state: Mapping[str, Any]) -> None:
    atomic_write(path, canonical_json_bytes(dict(state)))


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CollectionError(f"Invalid API updated_at timestamp: {value!r}") from error

    if parsed.tzinfo is None:
        raise CollectionError(f"API updated_at timestamp has no timezone: {value!r}")

    return parsed


def timestamp_with_overlap(value: str, seconds: int) -> str:
    return (parse_timestamp(value) - timedelta(seconds=seconds)).isoformat()


def query_fingerprint(params: Mapping[str, str]) -> str:
    encoded = json.dumps(dict(params), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save_document(output_directory: Path, document: Any) -> tuple[Path, bool]:
    if not isinstance(document, dict):
        raise CollectionError("A documents[] item is not a JSON object")

    document_id = document.get("id")

    if not isinstance(document_id, str) or not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        raise CollectionError(f"Unsafe or missing document id: {document_id!r}")

    updated_at = document.get("updated_at")

    if not isinstance(updated_at, str):
        raise CollectionError(f"Document {document_id} has no updated_at timestamp")

    parse_timestamp(updated_at)

    content = canonical_json_bytes(document)
    digest = hashlib.sha256(content).hexdigest()
    target = output_directory / document_id / f"{digest}.json"

    if target.exists():
        if target.read_bytes() != content:
            raise CollectionError(f"Hash collision or damaged snapshot: {target}")

        return target, False

    atomic_write(target, content)

    return target, True


class ApiClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, timeout: float, retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

        self.headers = {
            "Accept": "application/json",
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
            "User-Agent": "gigahack-municipal-corpus-collector/1.0",
        }

    def get_json(self, path: str, params: Mapping[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"

        if params:
            url = f"{url}?{urlencode(params)}"

        request = Request(url, headers=self.headers, method="GET")

        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    content_type = response.headers.get_content_type()

                    if content_type != "application/json":
                        raise CollectionError(f"Expected application/json from {url}, received {content_type}")

                    value = json.load(response)

                    if not isinstance(value, dict):
                        raise CollectionError(f"Expected a JSON object from {url}")

                    return value

            except HTTPError as error:
                retryable = error.code in {408, 429, 500, 502, 503, 504}

                if not retryable or attempt >= self.retries:
                    try:
                        detail = error.read(500).decode("utf-8", errors="replace")
                    except OSError:
                        detail = ""

                    raise CollectionError(f"API request failed with HTTP {error.code}: {detail or error.reason}") from error

                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt

            except (TimeoutError, URLError, OSError) as error:
                if attempt >= self.retries:
                    raise CollectionError(f"API request failed after retries: {error}") from error

                delay = 2 ** attempt

            time.sleep(delay + random.uniform(0, 0.25))

        raise AssertionError("unreachable")


def build_params(arguments: argparse.Namespace, updated_since: str | None) -> dict[str, str]:
    params = {
        "tiers": arguments.tiers,
        "limit": str(arguments.page_size),
        "text": "0" if arguments.metadata_only else "1",
        "ocr_pending": "1" if arguments.include_ocr_pending else "0",
    }

    for key in ("source", "category", "lang"):
        value = getattr(arguments, key)

        if value:
            params[key] = value

    if updated_since:
        params["updated_since"] = updated_since

    return params


def collect(arguments: argparse.Namespace, client: ApiClient) -> dict[str, Any]:
    output_directory = arguments.output_dir.expanduser().resolve()
    state_path = output_directory / DEFAULT_STATE_FILENAME
    state = read_state(state_path)

    base_params = build_params(arguments, None)
    scope_fingerprint = query_fingerprint(base_params)
    checkpoints = state.setdefault("checkpoints", {})

    if not isinstance(checkpoints, dict):
        raise CollectionError(f"Invalid checkpoints in {state_path}")

    checkpoint = checkpoints.get(scope_fingerprint, {})

    completed_updated_at = checkpoint.get("last_completed_updated_at") if isinstance(checkpoint, dict) else None

    if arguments.full:
        updated_since = None
    elif arguments.updated_since:
        parse_timestamp(arguments.updated_since)
        updated_since = arguments.updated_since
    elif isinstance(completed_updated_at, str):
        updated_since = timestamp_with_overlap(completed_updated_at, arguments.overlap_seconds)
    else:
        updated_since = None

    params = build_params(arguments, updated_since)
    fingerprint = query_fingerprint(params)

    active = state.get("active")

    if isinstance(active, dict) and active.get("fingerprint") == fingerprint:
        cursor = active.get("cursor")
        max_seen_updated_at = active.get("max_seen_updated_at")
    else:
        cursor = None
        max_seen_updated_at = None

        active = {
            "fingerprint": fingerprint,
            "scope_fingerprint": scope_fingerprint,
            "params": params,
            "cursor": None,
            "max_seen_updated_at": None,
        }

        state["active"] = active
        write_state(state_path, state)

    pages = 0
    seen = 0
    created = 0
    unchanged = 0

    while True:
        request_params = dict(params)

        if cursor:
            request_params["cursor"] = cursor

        payload = client.get_json("documents", request_params)
        documents = payload.get("documents")

        if not isinstance(documents, list):
            raise CollectionError("API response has no documents[] array")

        next_cursor = payload.get("next_cursor")

        if next_cursor is not None and not isinstance(next_cursor, str):
            raise CollectionError("API next_cursor is neither a string nor null")

        if next_cursor is not None and next_cursor == cursor:
            raise CollectionError("API returned the same non-null cursor twice")

        page_complete = True

        for document in documents:
            if arguments.max_documents is not None and seen >= arguments.max_documents:
                page_complete = False
                break

            _, was_created = save_document(output_directory, document)

            seen += 1
            created += int(was_created)
            unchanged += int(not was_created)

            updated_at = document["updated_at"]

            if max_seen_updated_at is None or parse_timestamp(updated_at) > parse_timestamp(max_seen_updated_at):
                max_seen_updated_at = updated_at

        if not page_complete:
            break

        pages += 1
        cursor = next_cursor

        active["cursor"] = cursor
        active["max_seen_updated_at"] = max_seen_updated_at
        state["active"] = active

        write_state(state_path, state)

        print(f"Downloaded page {pages} | Documents: {seen} | New snapshots: {created}", flush=True)

        if cursor is None:
            if max_seen_updated_at is not None:
                checkpoints[scope_fingerprint] = {
                    "last_completed_updated_at": max_seen_updated_at,
                    "params": base_params,
                }

            state["checkpoints"] = checkpoints
            state.pop("active", None)

            write_state(state_path, state)

            return {
                "status": "complete",
                "pages": pages,
                "documentsSeen": seen,
                "snapshotsCreated": created,
                "snapshotsUnchanged": unchanged,
                "lastCompletedUpdatedAt": checkpoints.get(scope_fingerprint, {}).get("last_completed_updated_at"),
                "outputDirectory": str(output_directory),
            }

        if arguments.max_documents is not None and seen >= arguments.max_documents:
            break

        if arguments.delay:
            time.sleep(arguments.delay)

    return {
        "status": "partial",
        "pages": pages,
        "documentsSeen": seen,
        "snapshotsCreated": created,
        "snapshotsUnchanged": unchanged,
        "message": "Stopped at --max-documents; run again without that option to finish.",
        "outputDirectory": str(output_directory),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect the Chisinau municipal corpus as one immutable JSON snapshot per document.")

    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--tiers", default="1,2", help="Comma-separated curation tiers.")
    parser.add_argument("--source")
    parser.add_argument("--category")
    parser.add_argument("--lang", choices=("ro", "ru", "en"))
    parser.add_argument("--updated-since", help="Explicit exclusive ISO timestamp boundary.")
    parser.add_argument("--full", action="store_true", help="Ignore the last completed timestamp.")
    parser.add_argument("--include-ocr-pending", action="store_true", help="Include documents whose pages are still waiting for OCR.")
    parser.add_argument("--metadata-only", action="store_true", help="Omit pages[] text from API responses.")
    parser.add_argument("--page-size", type=int, default=100, choices=range(1, 501), metavar="1..500")
    parser.add_argument("--max-documents", type=int, help="Stop early for a test run.")
    parser.add_argument("--overlap-seconds", type=int, default=300)
    parser.add_argument("--delay", type=float, default=0.05, help="Seconds between page requests.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=5)

    arguments = parser.parse_args()

    if arguments.max_documents is not None and arguments.max_documents < 1:
        parser.error("--max-documents must be at least 1")

    if arguments.overlap_seconds < 0:
        parser.error("--overlap-seconds cannot be negative")

    if arguments.delay < 0 or arguments.timeout <= 0 or arguments.retries < 0:
        parser.error("delay/retries cannot be negative and timeout must be positive")

    if arguments.full and arguments.updated_since:
        parser.error("--full and --updated-since cannot be combined")

    return arguments


def main() -> int:
    env_path = Path(__file__).resolve().parent / ".env"
    load_local_env(env_path)

    arguments = parse_arguments()

    client_id = read_environment_secret("CF_ACCESS_CLIENT_ID")
    client_secret = read_environment_secret("CF_ACCESS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(f"Error: CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET are missing. Expected .env at: {env_path}", file=sys.stderr)
        return 2

    client = ApiClient(arguments.base_url, client_id, client_secret, arguments.timeout, arguments.retries)

    try:
        result = collect(arguments, client)
    except (CollectionError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print("\nCollection finished:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
