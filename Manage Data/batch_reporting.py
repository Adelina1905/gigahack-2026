"""Shared run-manifest and review-report helpers for fault-isolated batches."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_core import DATA_DIRECTORY, managed_relative, safe_slug


DEFAULT_REVIEW_ROOT = DATA_DIRECTORY / "09_review"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def atomic_replace_json(path: Path, value: dict[str, Any]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read run manifest {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise RuntimeError(f"Unsupported run manifest: {path}")
    if not isinstance(value.get("documents"), list):
        raise RuntimeError(f"Run manifest has no documents list: {path}")
    return value


def issue_counts(documents: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "discovered": len(documents),
        "ready": sum(document.get("status") == "READY" for document in documents),
        "warning": sum(document.get("status") == "WARNING" for document in documents),
        "error": sum(document.get("status") == "ERROR" for document in documents),
    }


def refresh_review_outputs(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = read_manifest(manifest_path)
    documents = sorted(manifest["documents"], key=lambda item: str(item.get("documentId", "")))
    manifest["documents"] = documents
    manifest["counts"] = issue_counts(documents)
    atomic_replace_json(manifest_path, manifest)

    run_directory = manifest_path.parent
    documents_directory = run_directory / "documents"
    documents_directory.mkdir(parents=True, exist_ok=True)
    for document in documents:
        if document.get("status") not in {"WARNING", "ERROR"}:
            continue
        report_path = documents_directory / f"{safe_slug(str(document.get('documentId')))}.json"
        atomic_replace_json(report_path, {
            "schemaVersion": 1,
            "runId": manifest["runId"],
            **document,
        })

    database = manifest.get("database")
    if isinstance(database, dict) and (
        database.get("consistent") is False or database.get("globalError")
    ):
        status = "FAILED"
    elif manifest["counts"]["warning"] or manifest["counts"]["error"]:
        status = "PARTIAL_SUCCESS"
    else:
        status = "SUCCESS"
    summary = {
        "schemaVersion": 1,
        "runId": manifest["runId"],
        "status": status,
        "scope": manifest.get("scope"),
        "startedAt": manifest.get("startedAt"),
        "completedAt": manifest.get("completedAt"),
        "counts": manifest["counts"],
        "database": database,
        "runManifest": managed_relative(manifest_path),
        "reviewDirectory": managed_relative(run_directory),
    }
    atomic_replace_json(run_directory / "summary.json", summary)
    atomic_replace_json(run_directory.parent / "latest.json", {
        "schemaVersion": 1,
        "runId": manifest["runId"],
        "status": status,
        "summary": managed_relative(run_directory / "summary.json"),
        "runManifest": managed_relative(manifest_path),
    })
    return summary


def artifact_paths(stages: list[dict[str, Any]]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for stage in stages:
        stage_number = stage.get("stage")
        for key in ("manifest", "snapshot", "output"):
            value = stage.get(key)
            if isinstance(value, str) and value:
                artifacts[f"stage{stage_number}.{key}"] = managed_relative(Path(value))
    return artifacts
