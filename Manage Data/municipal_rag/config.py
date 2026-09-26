from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "rag.v3.json"


def load_dotenv(path: Path = ROOT.parent / ".env") -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class RagConfig:
    raw: dict[str, Any]

    @property
    def embedding_model(self) -> str:
        return self.raw["models"]["embedding"]

    @property
    def reranker_model(self) -> str:
        return self.raw["models"]["reranker"]

    @property
    def generator_model(self) -> str:
        return self.raw["models"]["generator"]

    @property
    def verifier_model(self) -> str:
        return self.raw["models"]["verifier"]

    @property
    def evidence_alias(self) -> str:
        return self.raw["collections"]["evidenceAlias"]

    @property
    def catalog_alias(self) -> str:
        return self.raw["collections"]["catalogAlias"]

    @property
    def preview_collection(self) -> str:
        return self.raw["collections"].get("previewCollection", "municipal_source_previews")

def load_config(path: Path | None = None) -> RagConfig:
    source = (path or DEFAULT_CONFIG).expanduser().resolve()
    value = json.loads(source.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != "3.0":
        raise ValueError(f"Unsupported RAG config schema in {source}")
    return RagConfig(value)

