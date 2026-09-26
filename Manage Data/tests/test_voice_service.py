from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from municipal_rag.api import ManagedAudioApiError
from municipal_rag.voice_service import OpenRouterVoiceService, speech_friendly_text
from municipal_rag.voice_service import SpeechAudio, Transcription


class VoiceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OpenRouterVoiceService(
            "secret-key",
            "openai/whisper-large-v3-turbo",
            "microsoft/mai-voice-2-flash",
            "en-US-Harper:MAI-Voice-2",
        )

    @patch("municipal_rag.voice_service.request_audio_json")
    def test_transcription_uses_exact_model_and_audio_contract(self, request) -> None:
        request.return_value = ({"text": " Bună ziua ", "language": "ro", "duration": 1.5}, "gen-1")
        encoded = base64.b64encode(b"audio bytes").decode("ascii")

        result = self.service.transcribe(encoded, "webm")

        self.assertEqual((result.text, result.language, result.duration_seconds), ("Bună ziua", "ro", 1.5))
        endpoint, payload, key = request.call_args.args
        self.assertEqual(endpoint, "audio/transcriptions")
        self.assertEqual(key, "secret-key")
        self.assertEqual(payload, {
            "model": "openai/whisper-large-v3-turbo",
            "input_audio": {"data": encoded, "format": "webm"},
        })
        self.assertNotIn("language", payload)

    def test_transcription_rejects_invalid_or_unsupported_audio_locally(self) -> None:
        for encoded, audio_format, status in (("not base64", "webm", 400),
                                               (base64.b64encode(b"x").decode(), "exe", 415)):
            with self.subTest(audio_format=audio_format), self.assertRaises(ManagedAudioApiError) as caught:
                self.service.transcribe(encoded, audio_format)
            self.assertEqual(caught.exception.status_code, status)

    @patch("municipal_rag.voice_service.request_audio_bytes")
    def test_speech_uses_mai_harper_mp3_and_cleans_markdown(self, request) -> None:
        request.return_value = (b"mp3", "audio/mpeg", "gen-2")

        result = self.service.synthesize("## Salut\n- Citiți [pagina](https://example.com). [S1]")

        self.assertEqual((result.data, result.content_type), (b"mp3", "audio/mpeg"))
        endpoint, payload, key = request.call_args.args
        self.assertEqual(endpoint, "audio/speech")
        self.assertEqual(key, "secret-key")
        self.assertEqual(payload["model"], "microsoft/mai-voice-2-flash")
        self.assertEqual(payload["voice"], "en-US-Harper:MAI-Voice-2")
        self.assertEqual(payload["response_format"], "mp3")
        self.assertNotIn("https://", payload["input"])
        self.assertNotIn("##", payload["input"])

    def test_markdown_cleanup_preserves_readable_content(self) -> None:
        self.assertEqual(
            speech_friendly_text("**Important**\n1. [Act](https://example.com)\n`code`"),
            "Important\nAct\ncode",
        )

    def test_internal_http_contract_returns_json_and_raw_audio(self) -> None:
        try:
            from fastapi.testclient import TestClient
            from municipal_rag.demo_service import DemoChatService
            from municipal_rag.server import create_app
        except ImportError:
            self.skipTest("requirements-server.txt is not installed")

        class FakeVoice:
            def transcribe(self, encoded_audio: str, audio_format: str) -> Transcription:
                self.transcription_call = (encoded_audio, audio_format)
                return Transcription("Salut", "ro", 1.25)

            def synthesize(self, text: str) -> SpeechAudio:
                self.speech_call = text
                return SpeechAudio(b"mp3", "audio/mpeg")

        voice = FakeVoice()
        client = TestClient(create_app(DemoChatService(), None, False, voice_service=voice))
        encoded = base64.b64encode(b"audio").decode("ascii")
        transcription = client.post("/v1/audio/transcriptions", json={
            "inputAudio": {"data": encoded, "format": "webm"},
        })
        speech = client.post("/v1/audio/speech", json={"text": "Answer"})

        self.assertEqual(transcription.status_code, 200)
        self.assertEqual(transcription.json(), {"text": "Salut", "language": "ro", "durationSeconds": 1.25})
        self.assertEqual(voice.transcription_call, (encoded, "webm"))
        self.assertEqual(speech.status_code, 200)
        self.assertEqual(speech.content, b"mp3")
        self.assertEqual(speech.headers["content-type"], "audio/mpeg")
        self.assertEqual(speech.headers["cache-control"], "no-store")


if __name__ == "__main__":
    unittest.main()
