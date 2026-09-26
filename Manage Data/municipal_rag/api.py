from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any


BASE = "https://openrouter.ai/api/v1"


class ManagedAudioApiError(RuntimeError):
    """Sanitized audio-provider failure with an HTTP status suitable for the API."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _audio_error(error: urllib.error.HTTPError) -> ManagedAudioApiError:
    if error.code == 429:
        return ManagedAudioApiError(429, "The speech provider is rate limited")
    if error.code in {400, 413, 415}:
        return ManagedAudioApiError(error.code, "The speech provider rejected the audio request")
    if error.code in {408, 504}:
        return ManagedAudioApiError(504, "The speech provider timed out")
    return ManagedAudioApiError(503, "The speech provider is unavailable")


def request_audio_json(endpoint: str, payload: dict[str, Any], api_key: str,
                       timeout: float = 90) -> tuple[dict[str, Any], str | None]:
    """Make one billable JSON audio request. Audio calls are intentionally not retried."""
    if not api_key:
        raise ManagedAudioApiError(503, "OPENROUTER_API_KEY is not configured")
    request = urllib.request.Request(
        f"{BASE}/{endpoint.lstrip('/')}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "User-Agent": "municipal-rag/3.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            generation_id = response.headers.get("X-Generation-Id")
    except urllib.error.HTTPError as error:
        raise _audio_error(error) from None
    except (TimeoutError, urllib.error.URLError):
        raise ManagedAudioApiError(504, "The speech provider timed out") from None
    except json.JSONDecodeError:
        raise ManagedAudioApiError(503, "The speech provider returned invalid JSON") from None
    if not isinstance(value, dict):
        raise ManagedAudioApiError(503, "The speech provider returned an invalid response")
    return value, generation_id


def request_audio_bytes(endpoint: str, payload: dict[str, Any], api_key: str,
                        timeout: float = 90) -> tuple[bytes, str, str | None]:
    """Make one billable request whose successful body is raw audio bytes."""
    if not api_key:
        raise ManagedAudioApiError(503, "OPENROUTER_API_KEY is not configured")
    request = urllib.request.Request(
        f"{BASE}/{endpoint.lstrip('/')}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "User-Agent": "municipal-rag/3.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get_content_type()
            generation_id = response.headers.get("X-Generation-Id")
    except urllib.error.HTTPError as error:
        raise _audio_error(error) from None
    except (TimeoutError, urllib.error.URLError):
        raise ManagedAudioApiError(504, "The speech provider timed out") from None
    if not data or not content_type.startswith("audio/"):
        raise ManagedAudioApiError(503, "The speech provider returned invalid audio")
    return data, content_type, generation_id


def request_json(endpoint: str, payload: dict[str, Any], api_key: str, timeout: float = 90, retries: int = 3) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            f"{BASE}/{endpoint.lstrip('/')}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": "municipal-rag/3.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("Managed API returned a non-object response")
            return value
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == retries:
                raise RuntimeError(f"Managed API HTTP {error.code}: {detail}") from error
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == retries:
                raise RuntimeError(f"Managed API unavailable: {error}") from error
        time.sleep(min(8, 2**attempt))
    raise RuntimeError("Managed API retry loop exhausted")


def chat_json(model: str, system: str, user: str, api_key: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    system = "Return one valid JSON object. " + system
    response_format: dict[str, Any] = {"type": "json_object"}
    if schema is not None:
        response_format = {"type": "json_schema", "json_schema": {"name": "municipal_structured_response", "strict": True, "schema": schema}}
    response = request_json("chat/completions", {
        "model": model,
        "temperature": 0,
        "response_format": response_format,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }, api_key)
    try:
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if isinstance(content, str):
            content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.I)
            if not content.startswith("{") and "{" in content and "}" in content:
                content = content[content.find("{"):content.rfind("}") + 1]
        value = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Managed chat model returned invalid structured JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("Managed chat model returned a non-object JSON value")
    value["_managedResponse"] = {"model": response.get("model"), "usage": response.get("usage")}
    return value


def embed(text: str, model: str, api_key: str) -> list[float]:
    response = request_json("embeddings", {"model": model, "input": text, "input_type": "search_query", "encoding_format": "float"}, api_key)
    try:
        vector = response["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Managed embedding model returned no vector") from error
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("Managed embedding model returned an invalid vector")
    return [float(value) for value in vector]


def chat_text(model: str, messages: list[dict[str, str]], api_key: str, temperature: float = 0.3) -> str:
    response = request_json("chat/completions", {"model": model, "temperature": temperature, "messages": messages}, api_key)
    try:
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Managed chat model returned a malformed response") from error
    if not isinstance(content, str):
        raise RuntimeError("Managed chat model returned no text content")
    return content.strip()
