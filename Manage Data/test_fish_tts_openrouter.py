"""Generate an MP3 with Fish Audio S2.1 Pro Free through OpenRouter."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "fish-audio/s2.1-pro-free:free"
MAX_REFERENCE_BYTES = 15 * 1024 * 1024
DEFAULT_TEXT = (
    "[warm] Bună ziua! Acesta este un test text-to-speech pentru proiectul "
    "GigaHack 2026."
)


def load_api_key() -> str:
    """Read the key from the environment or Manage Data/.env."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if api_key:
        return api_key

    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "OPENROUTER_API_KEY":
                return value.strip().strip("\"'")

    raise RuntimeError(
        "OPENROUTER_API_KEY is not set. Add it to your environment or "
        "to 'Manage Data/.env'."
    )


def reference_data_uri(audio_path: Path) -> str:
    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"Reference audio not found: {audio_path}")

    size = audio_path.stat().st_size
    if size == 0:
        raise ValueError("The reference audio file is empty.")
    if size > MAX_REFERENCE_BYTES:
        raise ValueError("Reference audio must be 15 MiB or smaller.")

    mime_type, _ = mimetypes.guess_type(audio_path.name)
    if not mime_type or not mime_type.startswith("audio/"):
        raise ValueError(
            "Could not identify the reference as audio. Use WAV, MP3, M4A, "
            "FLAC, OGG, AAC, or WebM."
        )

    encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def generate_speech(
    text: str,
    output_path: Path,
    voice: str | None,
    reference_audio: Path | None,
    reference_text: str | None,
) -> str | None:
    if not text.strip():
        raise ValueError("Text cannot be empty.")

    payload: dict[str, object] = {
        "model": MODEL,
        "input": text,
        "response_format": "mp3",
    }

    if voice:
        payload["voice"] = voice

    if reference_audio:
        references: list[dict[str, object]] = [
            {
                "type": "input_audio",
                "input_audio": {"data": reference_data_uri(reference_audio)},
            }
        ]
        if reference_text:
            references.append({"type": "text", "text": reference_text})
        payload["input_references"] = references

    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "GigaHack 2026 Fish Audio Test",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=90) as response:
            content_type = response.headers.get_content_type()
            audio = response.read()
            generation_id = response.headers.get("X-Generation-Id")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            details = body or exc.reason
        raise RuntimeError(f"OpenRouter returned HTTP {exc.code}:\n{details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach OpenRouter: {exc.reason}") from exc

    if not content_type.startswith("audio/"):
        raise RuntimeError(
            f"OpenRouter returned {content_type or 'an unknown content type'}, "
            "not audio."
        )
    if not audio:
        raise RuntimeError("OpenRouter returned an empty audio response.")

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)
    return generation_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Generate speech with {MODEL} through OpenRouter."
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=DEFAULT_TEXT,
        help="Text to speak; a short Romanian test is used when omitted",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="Read UTF-8 input text from a file instead of the text argument",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "fish_tts_output.mp3",
        help="Output MP3 path (default: Manage Data/fish_tts_output.mp3)",
    )

    voice_group = parser.add_mutually_exclusive_group()
    voice_group.add_argument(
        "--voice",
        help="Provider-supported voice identifier; omit for Fish Audio's default",
    )
    voice_group.add_argument(
        "--reference-audio",
        type=Path,
        help="Short audio sample whose voice should be imitated (maximum 15 MiB)",
    )
    parser.add_argument(
        "--reference-text",
        help="Optional exact transcript of --reference-audio for better cloning",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.reference_text and not args.reference_audio:
        print("Error: --reference-text requires --reference-audio.", file=sys.stderr)
        return 1

    try:
        text = (
            args.text_file.expanduser().read_text(encoding="utf-8")
            if args.text_file
            else args.text
        )
        generation_id = generate_speech(
            text=text,
            output_path=args.output,
            voice=args.voice,
            reference_audio=args.reference_audio,
            reference_text=args.reference_text,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Audio saved to: {args.output.expanduser().resolve()}")
    if generation_id:
        print(f"OpenRouter generation ID: {generation_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
