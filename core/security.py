"""Small security helpers shared by persistence and logging."""

from __future__ import annotations

import copy
import re


SECRET_KEYS = {
    "password",
    "passphrase",
    "secret",
    "token",
    "api_key",
    "private_key",
}

_SECRET_PATTERNS = [
    re.compile(
        rf"((?:{'|'.join(sorted(SECRET_KEYS))})\s*[=:]\s*)(\S+)",
        re.IGNORECASE,
    ),
]


def sanitize_for_export(value):
    """Deep-copy session data while dropping accidental secret fields."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                continue
            out[key] = sanitize_for_export(item)
        return out
    if isinstance(value, list):
        return [sanitize_for_export(item) for item in value]
    return copy.deepcopy(value)


def redact_text(value: object) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1<redacted>", text)
    return text
