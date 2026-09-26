from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING, Literal, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from .chat_service import ChatReply, ChatService, LlmUnavailableError
from .config import load_config, load_dotenv

if TYPE_CHECKING:
    from .rag_service import RagService


LOGGER = logging.getLogger(__name__)


class ReplyService(Protocol):
    def reply(self, message: str, history: list[dict[str, str]]) -> ChatReply: ...


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    chatId: uuid.UUID
    message: str
    history: list[HistoryItem] = Field(default_factory=list, max_length=50)

    @field_validator("message")
    @classmethod
    def message_length(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 8000:
            raise ValueError("message must be 1..8000 characters after trimming")
        return value


class Citation(BaseModel):
    title: str | None = None
    url: str | None = None
    exactQuote: str | None = None
    documentId: str | None = None


class ClarificationChoice(BaseModel):
    documentId: str
    label: str


class ChatResponse(BaseModel):
    mode: Literal["rag", "llm", "demo"]
    status: str
    answer: str
    citations: list[Citation]
    clarificationChoices: list[ClarificationChoice] | None = None


class HealthResponse(BaseModel):
    mode: Literal["live", "demo"]
    llmConfigured: bool
    ragAvailable: bool


def create_app(chat_service: ReplyService, rag: RagService | None, llm_configured: bool,
               *, mode: Literal["live", "demo"] = "live") -> FastAPI:
    app = FastAPI(title="Municipal chat service")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(mode=mode, llmConfigured=llm_configured,
                              ragAvailable=rag.is_available() if rag is not None else False)

    # Sync handler: blocking OpenRouter/Qdrant calls run in FastAPI's threadpool.
    @app.post("/v1/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        history = [item.model_dump() for item in request.history]
        try:
            reply = chat_service.reply(request.message, history)
        except LlmUnavailableError as error:
            LOGGER.warning("LLM unavailable for chat %s: %s", request.chatId, error)
            raise HTTPException(status_code=503, detail=str(error) or "LLM unavailable") from None
        return ChatResponse(mode=reply.mode, status=reply.status, answer=reply.answer,
            citations=[Citation(**{key: None if item.get(key) is None else str(item.get(key)) for key in Citation.model_fields}) for item in reply.citations],
            clarificationChoices=None if reply.clarification_choices is None else
                [ClarificationChoice(documentId=str(item.get("documentId")), label=str(item.get("label"))) for item in reply.clarification_choices])

    return app


def create_default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    mode = os.environ.get("CHAT_MODE", "live").strip().lower()
    if mode == "demo":
        from .demo_service import DemoChatService

        LOGGER.info("Chat service starting in explicit demo mode; no AI or Qdrant calls")
        return create_app(DemoChatService(), None, llm_configured=False, mode="demo")
    if mode != "live":
        raise ValueError("CHAT_MODE must be 'live' or 'demo'")
    return _create_live_app()


def _create_live_app() -> FastAPI:
    # Demo mode needs only the HTTP server dependencies, never live clients or an index.
    from qdrant_client import QdrantClient

    from .chat_model import OpenRouterChatModel
    from .rag_service import QdrantRagService

    config = load_config()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    qdrant_url = os.environ.get("QDRANT_URL", "").strip() or "http://localhost:6333"
    qdrant_key = os.environ.get("QDRANT_API_KEY", "").strip()
    client = QdrantClient(url=qdrant_url, api_key=qdrant_key or None, timeout=5)
    rag = QdrantRagService(client, config, qdrant_url)
    llm = OpenRouterChatModel(config.generator_model, api_key)
    LOGGER.info("Chat service starting: llmConfigured=%s qdrant=%s", bool(api_key), qdrant_url)
    return create_app(ChatService(rag, llm), rag, llm_configured=bool(api_key))
