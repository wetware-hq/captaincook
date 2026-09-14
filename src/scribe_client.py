"""OpenAI-compatible chat completions client for /scribe. Fail-closed if unset/down."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .scribe_md import system_prompt

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 60
USER_AGENT = "captaincook-scribe"


class ScribeNotConfiguredError(Exception):
    """SCRIBE_LLM_URL is missing. Fail-closed — no fake minutes."""


class ScribeServiceError(Exception):
    """LLM endpoint down, timed out, or returned an unparseable body. Fail-closed."""


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def resolve_endpoint(url: str | None = None) -> str:
    """Return the chat-completions URL. Raise if SCRIBE_LLM_URL is unset."""
    base = (url if url is not None else _env("SCRIBE_LLM_URL")).strip()
    if not base:
        raise ScribeNotConfiguredError("SCRIBE_LLM_URL is not set")
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def organise_minutes(
    source: str,
    *,
    url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout_sec: float = TIMEOUT_SEC,
) -> str:
    """POST chat completions; return assistant Markdown text.

    Raises ScribeNotConfiguredError when URL is missing.
    Raises ScribeServiceError on HTTP/timeout/parse failure.
    Never logs the full source at INFO.
    """
    endpoint = resolve_endpoint(url)
    key = api_key if api_key is not None else _env("SCRIBE_LLM_KEY")
    model_name = model if model is not None else _env("SCRIBE_LLM_MODEL")
    if not model_name:
        model_name = "default"

    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": source},
        ],
        "temperature": 0.2,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    logger.info(
        "scribe chat completions request chars=%s model=%s",
        len(source or ""),
        model_name,
    )

    req = Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read()
    except HTTPError as exc:
        raise ScribeServiceError("scribe LLM HTTP error") from exc
    except TimeoutError as exc:
        raise ScribeServiceError("scribe LLM timed out") from exc
    except URLError as exc:
        raise ScribeServiceError("scribe LLM was unreachable") from exc
    except OSError as exc:
        raise ScribeServiceError("scribe LLM request failed") from exc

    if status is not None and int(status) != 200:
        raise ScribeServiceError("scribe LLM returned a non-success status")

    return _parse_completion_body(raw)


def _parse_completion_body(raw: bytes | str) -> str:
    if raw is None:
        raise ScribeServiceError("scribe LLM returned an empty body")
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScribeServiceError("scribe LLM body was not UTF-8") from exc
    else:
        text = raw
    text = text.strip()
    if not text:
        raise ScribeServiceError("scribe LLM returned an empty body")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScribeServiceError("scribe LLM body was not JSON") from exc
    if not isinstance(data, dict):
        raise ScribeServiceError("scribe LLM JSON was not an object")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ScribeServiceError("scribe LLM JSON lacked choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ScribeServiceError("scribe LLM choice was unparseable")
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        # Some providers return content as a list of parts
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            joined = "".join(parts).strip()
            if joined:
                return joined
    # Legacy text field
    legacy = first.get("text")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    raise ScribeServiceError("scribe LLM response had no content")
