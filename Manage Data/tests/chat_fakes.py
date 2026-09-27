from __future__ import annotations

from typing import Any


class RecordingRag:
    """Hand-written RagService that returns a canned result and records questions and histories."""

    def __init__(self, available: bool, result: dict[str, Any] | None = None) -> None:
        self.available = available
        self.result = result or {}
        self.questions: list[str] = []
        self.histories: list[list[dict[str, str]] | None] = []

    def is_available(self) -> bool:
        return self.available

    def answer(self, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        self.questions.append(question)
        self.histories.append(history)
        return dict(self.result)
