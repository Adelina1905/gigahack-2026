from __future__ import annotations

from typing import Any


class RecordingRag:
    """Hand-written RagService that returns a canned result and records questions."""

    def __init__(self, available: bool, result: dict[str, Any] | None = None) -> None:
        self.available = available
        self.result = result or {}
        self.questions: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def answer(self, question: str) -> dict[str, Any]:
        self.questions.append(question)
        return dict(self.result)


class RecordingLlm:
    """Hand-written ChatModel that returns a fixed reply or raises, recording every call."""

    def __init__(self, reply: str = "llm reply", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply
