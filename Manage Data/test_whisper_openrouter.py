#!/usr/bin/env python3
"""Small OpenRouter Whisper transcription smoke test.

Uses only the Python standard library. The API key is read from the
OPENROUTER_API_KEY environment variable or from ``Manage Data/.env``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
MODEL = "openai/whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_FORMATS = {"aac", "flac", "m4a", "mp3", "ogg", "wav", "webm"}
RECORDING_SAMPLE_RATE = 16_000


def load_api_key() -> str:
    """Return the API key without printing or otherwise exposing it."""
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


def audio_format(audio_path: Path) -> str:
    file_format = audio_path.suffix.lower().lstrip(".")
    if file_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise ValueError(
            f"Unsupported audio format '.{file_format or '<none>'}'. "
            f"Use one of: {supported}."
        )
    return file_format


def sounddevice_module():
    try:
        import sounddevice  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Microphone recording requires the 'sounddevice' package. Install "
            "the Manage Data requirements with: "
            "python -m pip install -r 'Manage Data/requirements.txt'"
        ) from exc
    return sounddevice


def record_microphone(output_path: Path, seconds: float, device: str | None) -> None:
    if seconds <= 0:
        raise ValueError("Recording duration must be greater than zero.")

    sounddevice = sounddevice_module()
    print("Recording starts in:", flush=True)
    for remaining in range(3, 0, -1):
        print(f"  {remaining}", flush=True)
        time.sleep(1)

    print(f"Recording for {seconds:g} seconds... Speak now.", flush=True)
    selected_device: str | int | None = device
    if device and device.isdigit():
        selected_device = int(device)
    try:
        recording = sounddevice.rec(
            int(seconds * RECORDING_SAMPLE_RATE),
            samplerate=RECORDING_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=selected_device,
        )
        sounddevice.wait()
    except sounddevice.PortAudioError as exc:
        raise RuntimeError(f"Could not record from the microphone: {exc}") from exc

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(RECORDING_SAMPLE_RATE)
        wav_file.writeframes(recording.tobytes())
    print("Recording finished. Sending it to OpenRouter...", flush=True)


def transcribe(audio_path: Path, language: str | None) -> dict:
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    size = audio_path.stat().st_size
    if size == 0:
        raise ValueError("The audio file is empty.")
    if size > MAX_AUDIO_BYTES:
        raise ValueError(
            f"The audio file is {size / 1024 / 1024:.1f} MB; "
            "this test script accepts at most 25 MB."
        )

    payload: dict[str, object] = {
        "model": MODEL,
        "input_audio": {
            "data": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
            "format": audio_format(audio_path),
        },
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment"],
        "temperature": 0,
    }
    if language:
        payload["language"] = language

    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {load_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/",
            "X-OpenRouter-Title": "GigaHack 2026 Whisper Test",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=70) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.dumps(json.loads(body), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            details = body or exc.reason
        raise RuntimeError(f"OpenRouter returned HTTP {exc.code}:\n{details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach OpenRouter: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Transcribe one audio file with {MODEL} through OpenRouter."
    )
    parser.add_argument(
        "audio_file",
        type=Path,
        nargs="?",
        help="Existing audio file. Omit it to record from the microphone.",
    )
    parser.add_argument(
        "--language",
        help="Optional ISO-639-1 language hint, for example ro, ru, or en",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete JSON response after the transcript",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10,
        help="Microphone recording duration when no audio file is given (default: 10)",
    )
    parser.add_argument(
        "--device",
        help="Optional microphone device name or index",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_devices:
        try:
            print(sounddevice_module().query_devices())
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        if args.audio_file:
            result = transcribe(args.audio_file.expanduser().resolve(), args.language)
        else:
            with tempfile.TemporaryDirectory(prefix="gigahack-whisper-") as temp_dir:
                recording_path = Path(temp_dir) / "microphone.wav"
                record_microphone(recording_path, args.seconds, args.device)
                result = transcribe(recording_path, args.language)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("\nTranscript\n----------")
    print(result.get("text", ""))

    metadata = []
    if result.get("language") is not None:
        metadata.append(f"language: {result['language']}")
    if result.get("duration") is not None:
        metadata.append(f"duration: {result['duration']} seconds")
    usage = result.get("usage")
    if isinstance(usage, dict) and usage.get("cost") is not None:
        metadata.append(f"cost: ${usage['cost']}")
    if metadata:
        print("\n" + " | ".join(metadata))

    if args.json:
        print("\nFull response\n-------------")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
