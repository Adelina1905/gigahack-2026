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

    def answer(self, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]: ...


class QdrantRagService:
    """RAG answering over the evidence alias; availability is probed read-only and cached.

    A confirmed state is cached for `cache_seconds` when available and `failure_cache_seconds` when not. A probe that
    errors (timeout, connection reset) keeps the last known-good state, so one slow probe under load cannot reject
    requests; without a known-good state it counts as unavailable, cached only briefly.
    """

    def __init__(self, client: QdrantClient, config: RagConfig, qdrant_url: str,
                 clock: Callable[[], float] = time.monotonic, cache_seconds: float = 60.0,
                 failure_cache_seconds: float = 5.0) -> None:
        self._client = client
        self._config = config
        self._qdrant_url = qdrant_url
        self._clock = clock
        self._cache_seconds = cache_seconds
        self._failure_cache_seconds = failure_cache_seconds
        self._cached: tuple[float, bool] | None = None
        self._known_good = False

    def is_available(self) -> bool:
        now = self._clock()
        if self._cached is not None:
            checked, available = self._cached
            if now - checked < (self._cache_seconds if available else self._failure_cache_seconds):
                return available
        try:
            available = self._probe()
        except Exception as error:
            LOGGER.warning("Qdrant availability check failed: %s", error)
            # Transient error: trust the last confirmed state, and probe again soon.
            self._cached = (now - self._cache_seconds + self._failure_cache_seconds, True) if self._known_good else (now, False)
            return self._known_good
        self._known_good = available
        self._cached = (now, available)
        return available

    def _probe(self) -> bool:
        """True when the evidence alias exists and has points; raises on transport errors."""
        alias = self._config.evidence_alias
        aliases = self._client.get_aliases().aliases
        if not any(item.alias_name == alias for item in aliases):
            return False
        # An approximate count is instant; an exact count scans 600k+ points and times out under load.
        return self._client.count(collection_name=alias, exact=False).count > 0

    def answer(self, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        result = answering.answer(question, qdrant_url=self._qdrant_url, history=history or [])
        try:
            write_trace(result, int((time.monotonic() - started) * 1000), self._config.raw["models"])
        except OSError:
            pass
        result.pop("_trace", None)
        return result
