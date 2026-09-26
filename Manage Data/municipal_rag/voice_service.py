from __future__ import annotations

import base64
import binascii
import logging
import re
import time
from dataclasses import dataclass

from .api import ManagedAudioApiError, request_audio_bytes, request_audio_json


LOGGER = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 10 * 1024 * 1024
SUPPORTED_FORMATS = {"aac", "flac", "m4a", "mp3", "mp4", "ogg", "wav", "webm"}
# ISO-639-1 hints the UI can send: its languages (Romanian, Russian, English).
SUPPORTED_LANGUAGES = {"ro", "ru", "en"}


@dataclass(frozen=True)
class Transcription:
    text: str
    language: str | None
    duration_seconds: float | None


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    content_type: str


def speech_friendly_text(value: str) -> str:
    """Remove Markdown mechanics and URLs while preserving readable answer content."""
    text = re.sub(r"```(?:[^\n]*)\n?(.*?)```", r"\1", value, flags=re.DOTALL)
    text = re.sub(r"!\[([^]]*)]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[ \t]*\[S\d+\]", "", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)", "", text)
    text = re.sub(r"[*_~`]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class OpenRouterVoiceService:
    def __init__(self, api_key: str, stt_model: str, tts_model: str, tts_voice: str) -> None:
        self._api_key = api_key
        self._stt_model = stt_model
        self._tts_model = tts_model
        self._tts_voice = tts_voice

    def transcribe(self, encoded_audio: str, audio_format: str,
                   language: str | None = None) -> Transcription:
        normalized_format = audio_format.strip().lower()
        if normalized_format not in SUPPORTED_FORMATS:
            raise ManagedAudioApiError(415, "Unsupported audio format")
        normalized_language = language.strip().lower() if language else None
        if normalized_language is not None and normalized_language not in SUPPORTED_LANGUAGES:
            raise ManagedAudioApiError(400, "Unsupported language hint")
        try:
            decoded = base64.b64decode(encoded_audio, validate=True)
        except (binascii.Error, ValueError):
            raise ManagedAudioApiError(400, "Audio data is not valid base64") from None
        if not decoded:
            raise ManagedAudioApiError(400, "Audio recording is empty")
        if len(decoded) > MAX_AUDIO_BYTES:
            raise ManagedAudioApiError(413, "Audio recording exceeds 10 MB")

        started = time.monotonic()
        payload: dict[str, object] = {
            "model": self._stt_model,
            "input_audio": {"data": encoded_audio, "format": normalized_format},
        }
        # The UI language at request time; without it the provider detects the language itself.
        if normalized_language is not None:
            payload["language"] = normalized_language
        result, generation_id = request_audio_json("audio/transcriptions", payload, self._api_key)
        text = result.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ManagedAudioApiError(503, "The speech provider returned an empty transcript")
        duration = result.get("duration")
        usage = result.get("usage")
        if duration is None and isinstance(usage, dict):
            duration = usage.get("seconds")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
        language = result.get("language")
        LOGGER.info("Speech transcription completed model=%s format=%s languageHint=%s elapsedMs=%d generationId=%s",
                    self._stt_model, normalized_format, normalized_language or "-",
                    int((time.monotonic() - started) * 1000),
                    generation_id or "-")
        return Transcription(text.strip(), language if isinstance(language, str) else None,
                             duration_seconds)

    def synthesize(self, text: str) -> SpeechAudio:
        cleaned = speech_friendly_text(text)
        if not cleaned:
            raise ManagedAudioApiError(400, "There is no readable answer text")
        if len(cleaned) > 8000:
            raise ManagedAudioApiError(400, "Speech text exceeds 8,000 characters")
        started = time.monotonic()
        data, content_type, generation_id = request_audio_bytes("audio/speech", {
            "model": self._tts_model,
            "input": cleaned,
            "voice": self._tts_voice,
            "response_format": "mp3",
        }, self._api_key)
        LOGGER.info("Speech synthesis completed model=%s elapsedMs=%d generationId=%s",
                    self._tts_model, int((time.monotonic() - started) * 1000), generation_id or "-")
        return SpeechAudio(data, content_type)
