from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .chat_model import ChatModel
from .rag_service import RagService


DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant for residents of Chișinău municipality. "
    "Answer in the user's language: Romanian or Russian, otherwise match the language the user writes in. "
    "Be concise. Say plainly when you are not sure or do not have official information, "
    "and never invent municipal facts, dates or numbers."
)

RAG_STATUSES = {"SUPPORTED", "PARTIAL", "CONTRADICTION", "NEEDS_CLARIFICATION"}
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
            result = self._rag.answer(message)
            status = str(result.get("status") or "")
            if status in RAG_STATUSES:
                return self._rag_reply(status, result)
        return self._llm_reply(message, history)

    @staticmethod
    def _rag_reply(status: str, result: dict[str, Any]) -> ChatReply:
        citations = [{"title": item.get("title"), "url": item.get("url"), "exactQuote": item.get("exactQuote"),
                      "documentId": item.get("documentId")} for item in result.get("citations") or []]
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
