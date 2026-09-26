"""Generate an MP3 with Microsoft MAI-Voice-2-Flash through OpenRouter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://openrouter.ai/api/v1/audio/speech"
MODEL = "microsoft/mai-voice-2-flash"
VOICES = (
    "en-US-Harper:MAI-Voice-2",
    "es-MX-Valeria:MAI-Voice-2",
    "fr-FR-Soleil:MAI-Voice-2",
    "de-DE-Klaus:MAI-Voice-2",
)
DEFAULT_TEXT = "Hello! This is a MAI Voice 2 Flash test for GigaHack 2026."


def load_api_key() -> str:
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


def generate_speech(
    text: str,
    output_path: Path,
    voice: str,
    speed: float,
    style: str | None,
    style_degree: float,
) -> str | None:
    if not text.strip():
        raise ValueError("Text cannot be empty.")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0.")
    if style_degree <= 0:
        raise ValueError("Style degree must be greater than zero.")

    payload: dict[str, object] = {
        "model": MODEL,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "speed": speed,
    }
    if style:
        payload["provider"] = {
            "options": {
                "azure": {
                    "style": style,
                    "styledegree": style_degree,
                }
            }
        }

    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": "GigaHack 2026 MAI Voice Test",
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
        help="Text to speak; an English test sentence is used when omitted",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="Read UTF-8 input text from a file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "mai_voice_output.mp3",
        help="Output MP3 path (default: Manage Data/mai_voice_output.mp3)",
    )
    parser.add_argument(
        "--voice",
        choices=VOICES,
        default=VOICES[0],
        help="Voice to use (default: en-US-Harper)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speaking speed from 0.5 to 2.0 (default: 1.0)",
    )
    parser.add_argument(
        "--style",
        help="Azure speaking style, such as cheerful, sad, angry, or excited",
    )
    parser.add_argument(
        "--style-degree",
        type=float,
        default=1.0,
        help="Style intensity when --style is supplied (default: 1.0)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
            speed=args.speed,
            style=args.style,
            style_degree=args.style_degree,
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
