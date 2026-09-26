from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .chat_model import ChatModel
    from .rag_service import RagService


DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant for residents of Chișinău municipality. "
    "Answer in the user's language: Romanian or Russian, otherwise match the language the user writes in. "
    "Be concise. Say plainly when you are not sure or do not have official information, "
    "and never invent municipal facts, dates or numbers."
)

RAG_STATUSES = {"SUPPORTED", "PARTIAL", "NOT_FOUND", "CONTRADICTION", "NEEDS_CLARIFICATION"}
HISTORY_ROLES = {"user", "assistant"}


@dataclass(frozen=True)
class ChatReply:
    mode: str
    status: str
    answer: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    clarification_choices: list[dict[str, Any]] | None = None


class LlmUnavailableError(Exception):
    pass


class ChatService:
    """Routes a chat turn to grounded RAG when the index can answer, otherwise to the plain LLM."""

    def __init__(self, rag: RagService, llm: ChatModel, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._rag = rag
        self._llm = llm
        self._system_prompt = system_prompt

    def reply(self, message: str, history: list[dict[str, str]]) -> ChatReply:
        if self._rag.is_available():
            question = self._clarified_question(message, history)
            result = self._rag.answer(question)
            status = str(result.get("status") or "")
            if status in RAG_STATUSES:
                return self._rag_reply(status, result)
            if status == "UNAVAILABLE":
                reasons = (result.get("confidence") or {}).get("reasons") or []
                raise LlmUnavailableError(str(reasons[0]) if reasons else "RAG service unavailable")
        return self._llm_reply(message, history)

    @staticmethod
    def _clarified_question(message: str, history: list[dict[str, str]]) -> str:
        """Restore the original question when the user selects a clarification choice."""
        if len(history) < 2 or history[-1].get("role") != "assistant" or history[-2].get("role") != "user":
            return message
        choices = [value.strip() for value in re.findall(r"(?m)^-\s+(.+?)\s*$", history[-1].get("content", ""))]
        selected = message.strip()
        if selected not in choices:
            return message
        original = history[-2].get("content", "").strip()
        if not original:
            return message
        return f'{original}\nDocument selectat pentru clarificare: "{selected}"'

    @staticmethod
    def _rag_reply(status: str, result: dict[str, Any]) -> ChatReply:
        fields = ("id", "evidenceId", "versionId", "title", "url", "exactQuote", "documentId", "sourceFile", "locator")
        citations = [{field: item.get(field) for field in fields} for item in result.get("citations") or []]
        if status == "NEEDS_CLARIFICATION":
            return ChatReply("rag", status, str(result.get("clarificationQuestion") or ""), citations,
                             list(result.get("clarificationChoices") or []))
        return ChatReply("rag", status, str(result.get("answer") or ""), citations, None)

    def _llm_reply(self, message: str, history: list[dict[str, str]]) -> ChatReply:
        messages = [{"role": "system", "content": self._system_prompt}]
        messages += [{"role": item["role"], "content": item["content"]} for item in history if item.get("role") in HISTORY_ROLES]
        messages.append({"role": "user", "content": message})
        try:
            text = self._llm.complete(messages)
        except Exception as error:
            raise LlmUnavailableError(str(error)) from error
        return ChatReply("llm", "LLM", text, [], None)
