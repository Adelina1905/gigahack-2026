from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

from qdrant_client import QdrantClient

from . import answering
from .config import RagConfig
from .tracing import write_trace


LOGGER = logging.getLogger(__name__)


class RagService(Protocol):
    def is_available(self) -> bool: ...

    def answer(self, question: str) -> dict[str, Any]: ...


class QdrantRagService:
    """RAG answering over the evidence alias; availability is probed read-only and cached."""

    def __init__(self, client: QdrantClient, config: RagConfig, qdrant_url: str,
                 clock: Callable[[], float] = time.monotonic, cache_seconds: float = 60.0) -> None:
        self._client = client
        self._config = config
        self._qdrant_url = qdrant_url
        self._clock = clock
        self._cache_seconds = cache_seconds
        self._cached: tuple[float, bool] | None = None

    def is_available(self) -> bool:
        now = self._clock()
        if self._cached is not None and now - self._cached[0] < self._cache_seconds:
            return self._cached[1]
        available = self._probe()
        self._cached = (now, available)
        return available

    def _probe(self) -> bool:
        alias = self._config.evidence_alias
        try:
            aliases = self._client.get_aliases().aliases
            if not any(item.alias_name == alias for item in aliases):
                return False
            return self._client.count(collection_name=alias, exact=True).count > 0
        except Exception as error:
            LOGGER.warning("Qdrant availability check failed: %s", error)
            return False

    def answer(self, question: str) -> dict[str, Any]:
        started = time.monotonic()
        result = answering.answer(question, qdrant_url=self._qdrant_url)
        try:
            write_trace(result, int((time.monotonic() - started) * 1000), self._config.raw["models"])
        except OSError:
            pass
        result.pop("_trace", None)
        return result
