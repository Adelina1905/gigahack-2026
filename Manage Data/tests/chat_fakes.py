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
