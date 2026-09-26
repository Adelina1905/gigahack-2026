from __future__ import annotations

from .chat_service import ChatReply


class DemoChatService:
    """Deterministic integration replies with no AI, retrieval, or network calls."""

    def reply(self, message: str, history: list[dict[str, str]]) -> ChatReply:
        prior_turns = sum(item.get("role") == "user" for item in history)
        answer = (
            f"Python received your message ({len(message)} characters) and "
            f"{prior_turns} earlier user message(s). "
            "This deterministic reply is for checking chat integration and saved conversations. "
            "It is not an AI answer or official municipal information.\n\n"
            "Example link for testing: https://example.com "
            "(demonstration only; not a supporting source)."
        )
        return ChatReply(mode="demo", status="DEMO", answer=answer)
