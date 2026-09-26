from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator

from .alerts import AlertService, TopicQuery, create_alert_service
from .api import ManagedAudioApiError
from .chat_service import ChatReply, ChatService, LlmUnavailableError
from .config import load_config, load_dotenv
from .voice_service import OpenRouterVoiceService
from .source_preview import SourcePreviewNotFound, SourcePreviewUnavailable

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
    id: str | None = None
    evidenceId: str | None = None
    versionId: str | None = None
    title: str | None = None
    url: str | None = None
    exactQuote: str | None = None
    documentId: str | None = None
    sourceFile: str | None = None
    locator: dict[str, Any] | None = None


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


class SourcePreviewService(Protocol):
    def preview(self, document_id: str, version_id: str | None, focus_evidence_id: str | None,
                start: int | None, limit: int) -> dict[str, Any]: ...


class SourceSection(BaseModel):
    id: str
    order: int
    headingPath: list[str]
    text: str
    locator: dict[str, Any]


class SourcePreviewResponse(BaseModel):
    documentId: str
    versionId: str
    title: str
    sourceUrl: str | None = None
    sourceFile: str | None = None
    sourceKind: Literal["web", "pdf", "text"]
    publishedDate: str | None = None
    totalSections: int
    start: int
    focusIndex: int | None = None
    focusSectionId: str | None = None
    hasPrevious: bool
    hasNext: bool
    sections: list[SourceSection]


class InputAudio(BaseModel):
    data: str = Field(min_length=1, max_length=14_000_000)
    format: str


class TranscriptionRequest(BaseModel):
    inputAudio: InputAudio
    # The UI language when the recording was sent, used as the speech-to-text language hint.
    language: Literal["ro", "ru", "en"] | None = None


class TranscriptionResponse(BaseModel):
    text: str
    language: str | None = None
    durationSeconds: float | None = None


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class AlertTopicsRequest(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=50)
    existingLabels: list[str] = Field(default_factory=list, max_length=50)


class AlertTopic(BaseModel):
    label: str
    query: str


class AlertTopicsResponse(BaseModel):
    topics: list[AlertTopic]


class AlertTopicIn(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    minScore: float | None = None


class AlertMatchRequest(BaseModel):
    topics: list[AlertTopicIn] = Field(min_length=1, max_length=50)
    excludedDocumentIds: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)


class AlertMatchOut(BaseModel):
    topicId: str
    documentId: str
    title: str
    url: str | None = None
    source: str | None = None
    district: str | None = None
    category: str | None = None
    publishedDate: str | None = None
    excerpt: str
    score: float


class AlertMatchResponse(BaseModel):
    matcher: Literal["embedding", "lexical"]
    matches: list[AlertMatchOut]


def create_app(chat_service: ReplyService, rag: RagService | None, llm_configured: bool,
               *, mode: Literal["live", "demo"] = "live",
               voice_service: OpenRouterVoiceService | None = None,
               alert_service: AlertService | None = None,
               source_preview_service: SourcePreviewService | None = None) -> FastAPI:
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
            citations=[Citation(**{key: item.get(key) if key == "locator" else
                (None if item.get(key) is None else str(item.get(key))) for key in Citation.model_fields})
                for item in reply.citations],
            clarificationChoices=None if reply.clarification_choices is None else
                [ClarificationChoice(documentId=str(item.get("documentId")), label=str(item.get("label"))) for item in reply.clarification_choices])

    @app.get("/v1/sources/{document_id}/preview", response_model=SourcePreviewResponse)
    def source_preview(document_id: str, versionId: str | None = None,
                       focusEvidenceId: str | None = None, start: int | None = None,
                       limit: int = 40) -> SourcePreviewResponse:
        if source_preview_service is None:
            raise HTTPException(status_code=503, detail="Source preview is unavailable")
        if not 1 <= len(document_id) <= 256 or limit < 1 or limit > 100 or (start is not None and start < 0):
            raise HTTPException(status_code=400, detail="Invalid source preview request")
        try:
            return SourcePreviewResponse(**source_preview_service.preview(
                document_id, versionId, focusEvidenceId, start, limit))
        except SourcePreviewNotFound:
            raise HTTPException(status_code=404, detail="Source preview not found") from None
        except SourcePreviewUnavailable:
            raise HTTPException(status_code=503, detail="Source preview is unavailable") from None

    @app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
    def transcribe(request: TranscriptionRequest) -> TranscriptionResponse:
        if voice_service is None:
            raise HTTPException(status_code=503, detail="Speech service is unavailable")
        try:
            result = voice_service.transcribe(request.inputAudio.data, request.inputAudio.format,
                                              request.language)
        except ManagedAudioApiError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from None
        return TranscriptionResponse(text=result.text, language=result.language,
                                     durationSeconds=result.duration_seconds)

    @app.post("/v1/audio/speech")
    def speech(request: SpeechRequest) -> Response:
        if voice_service is None:
            raise HTTPException(status_code=503, detail="Speech service is unavailable")
        try:
            result = voice_service.synthesize(request.text)
        except ManagedAudioApiError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from None
        return Response(content=result.data, media_type=result.content_type,
                        headers={"Cache-Control": "no-store"})

    @app.post("/v1/alerts/topics", response_model=AlertTopicsResponse)
    def alert_topics(request: AlertTopicsRequest) -> AlertTopicsResponse:
        if alert_service is None:
            raise HTTPException(status_code=503, detail="Alert service is unavailable")
        topics = alert_service.topics(request.questions, request.existingLabels)
        return AlertTopicsResponse(topics=[AlertTopic(label=item.label, query=item.query) for item in topics])

    @app.post("/v1/alerts/match", response_model=AlertMatchResponse)
    def alert_match(request: AlertMatchRequest) -> AlertMatchResponse:
        if alert_service is None:
            raise HTTPException(status_code=503, detail="Alert service is unavailable")
        result = alert_service.match([TopicQuery(item.id, item.query, item.minScore) for item in request.topics],
                                     request.excludedDocumentIds, request.limit)
        return AlertMatchResponse(matcher=result.matcher, matches=[AlertMatchOut(
            topicId=item.topic_id, documentId=item.document.document_id, title=item.document.title,
            url=item.document.url, source=item.document.source, district=item.document.district,
            category=item.document.category, publishedDate=item.document.published_date,
            excerpt=item.document.excerpt, score=item.score) for item in result.matches])

    return app


def create_default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    mode = os.environ.get("CHAT_MODE", "live").strip().lower()
    if mode == "demo":
        from .demo_service import DemoChatService

        LOGGER.info("Chat service starting in explicit demo mode; no AI or Qdrant calls")
        return create_app(DemoChatService(), None, llm_configured=False, mode="demo",
                          alert_service=create_alert_service("", "", "", use_ai=False))
    if mode != "live":
        raise ValueError("CHAT_MODE must be 'live' or 'demo'")
    return _create_live_app()


def _create_live_app() -> FastAPI:
    # Demo mode needs only the HTTP server dependencies, never live clients or an index.
    from qdrant_client import QdrantClient

    from .chat_model import OpenRouterChatModel
    from .rag_service import QdrantRagService
    from .source_preview import QdrantSourcePreviewService

    config = load_config()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    qdrant_url = os.environ.get("QDRANT_URL", "").strip() or "http://localhost:6333"
    qdrant_key = os.environ.get("QDRANT_API_KEY", "").strip()
    client = QdrantClient(url=qdrant_url, api_key=qdrant_key or None, timeout=5)
    rag = QdrantRagService(client, config, qdrant_url)
    llm = OpenRouterChatModel(config.generator_model, api_key)
    voice = OpenRouterVoiceService(
        api_key,
        os.environ.get("OPENROUTER_STT_MODEL", "openai/whisper-large-v3-turbo").strip(),
        os.environ.get("OPENROUTER_TTS_MODEL", "microsoft/mai-voice-2-flash").strip(),
        os.environ.get("OPENROUTER_TTS_VOICE", "en-US-Harper:MAI-Voice-2").strip(),
    )
    LOGGER.info("Chat service starting: llmConfigured=%s qdrant=%s", bool(api_key), qdrant_url)
    alerts = create_alert_service(api_key, config.embedding_model, config.generator_model)
    previews = QdrantSourcePreviewService(client, config.preview_collection)
    return create_app(ChatService(rag, llm), rag, llm_configured=bool(api_key),
                      voice_service=voice, alert_service=alerts, source_preview_service=previews)
