from __future__ import annotations

from typing import Protocol

from .api import chat_text


class ChatModel(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


class OpenRouterChatModel:
    """Free-form chat completion through OpenRouter; errors never echo the API key."""

    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    def complete(self, messages: list[dict[str, str]]) -> str:
        try:
            return chat_text(self._model, messages, self._api_key)
        except Exception as error:
            reason = str(error)
            if self._api_key:
                reason = reason.replace(self._api_key, "***")
            raise RuntimeError(reason) from None
