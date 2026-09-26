from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TRACE = Path(__file__).resolve().parents[1] / "data" / "10_traces" / "queries.jsonl"


def write_trace(result: dict[str, Any], elapsed_ms: int, models: dict[str, str], path: Path = DEFAULT_TRACE) -> None:
    """Append a secret-free trace using atomic file replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    question = str(result.get("question") or "")
    trace = {
        "at": datetime.now(timezone.utc).isoformat(), "schemaVersion": result.get("schemaVersion"),
        "questionSha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "language": result.get("detectedLanguage"), "status": result.get("status"),
        "elapsedMs": elapsed_ms, "models": models,
        "ranks": [{"evidenceId": item.get("evidenceId"), **(item.get("retrieval") or {})} for item in result.get("citations", [])],
        "verifierDecisions": (result.get("_trace") or {}).get("verifierDecisions", []),
        "generation": (result.get("_trace") or {}).get("generation"),
    }
    existing = path.read_bytes() if path.exists() else b""
    content = existing + json.dumps(trace, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False, prefix=".trace-", suffix=".tmp") as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno()); temporary = Path(stream.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
