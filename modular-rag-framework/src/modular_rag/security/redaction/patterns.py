"""PII and secret redaction patterns (V4)."""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("phone_fr_local", re.compile(r"\b0[1-9](?:[\s.-]?\d{2}){4}\b")),
    ("phone_fr_intl", re.compile(r"\+33\s?[1-9](?:[\s.-]?\d{2}){4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|api|token)[-_][A-Za-z0-9]{20,}\b", re.I)),
]

_PLACEHOLDER = "[REDACTED]"


class PatternRedactor:
    """Replace PII and secret patterns in text with [REDACTED]."""

    def name(self) -> str:
        return "pattern-redactor"

    def redact(self, text: str) -> str:
        for _label, pattern in _PATTERNS:
            text = pattern.sub(_PLACEHOLDER, text)
        return text
