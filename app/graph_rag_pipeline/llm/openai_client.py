"""Small OpenAI API wrapper for optional answer polishing.

The wrapper deliberately avoids logging secrets and returns None on failure so
callers can fall back to deterministic answers.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 20


def api_key_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def call_polish_llm(system_prompt: str, user_prompt: str) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    try:
        timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return str(content).strip() or None

