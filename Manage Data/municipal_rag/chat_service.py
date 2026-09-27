from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .guardrails import CONFLICT_REASON, NOT_FOUND_REASONS

if TYPE_CHECKING:
    from .rag_service import RagService


RAG_STATUSES = {"SUPPORTED", "PARTIAL", "CONTRADICTION", "NEEDS_CLARIFICATION", "NOT_FOUND"}
CITATION_FIELDS = ("id", "evidenceId", "versionId", "title", "url", "exactQuote", "documentId", "sourceFile", "locator",
                   "publisher", "publishedDate", "outdated")


@dataclass(frozen=True)
class ChatReply:
    mode: str
    status: str
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    clarification_choices: list[dict[str, Any]] | None = None
    reason: str | None = None
    flags: list[str] = field(default_factory=list)


class LlmUnavailableError(Exception):
    pass


class ChatService:
    """Answers only from the municipal document index; it never falls back to an ungrounded LLM reply."""

    def __init__(self, rag: RagService) -> None:
        self._rag = rag

    def reply(self, message: str, history: list[dict[str, str]]) -> ChatReply:
        if not self._rag.is_available():
            raise LlmUnavailableError("The municipal document index is not available")
        result = self._rag.answer(message, history)
        status = str(result.get("status") or "")
        if status not in RAG_STATUSES:
            reasons = (result.get("confidence") or {}).get("reasons") or []
            raise LlmUnavailableError(str(reasons[0]) if reasons else "The municipal document search failed")
        return self._rag_reply(status, result)

    @staticmethod
    def _rag_reply(status: str, result: dict[str, Any]) -> ChatReply:
        citations = [{**{field: item.get(field) for field in CITATION_FIELDS}, "outdated": item.get("outdated") is True}
                     for item in result.get("citations") or []]
        flags = [str(value) for value in result.get("flags") or []]
        if status == "NEEDS_CLARIFICATION":
            return ChatReply("rag", status, str(result.get("clarificationQuestion") or result.get("answer") or ""), citations,
                             list(result.get("clarificationChoices") or []), None, flags)
        if status == "NOT_FOUND":
            # The contract: a NOT_FOUND answer never carries citations and always says why.
            reason = result.get("reason") if result.get("reason") in NOT_FOUND_REASONS else "NO_RELEVANT_EVIDENCE"
            return ChatReply("rag", status, str(result.get("answer") or ""), [], None, reason, flags)
        reason = CONFLICT_REASON if status == "CONTRADICTION" else None
        return ChatReply("rag", status, str(result.get("answer") or ""), citations, None, reason, flags)
