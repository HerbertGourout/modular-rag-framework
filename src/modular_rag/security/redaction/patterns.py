"""PII and secret redaction patterns (V4)."""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("phone_fr_local", re.compile(r"\b0[1-9](?:[\s.-]?\d{2}){4}\b")),
    ("phone_fr_intl", re.compile(r"\+33\s?[1-9](?:[\s.-]?\d{2}){4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|api|token)[-_][A-Za-z0-9]{20,}\b", re.I)),
    ("ssn_us", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]

_CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\d\b")

_PLACEHOLDER = "[REDACTED]"


def _luhn_valid(candidate: str) -> bool:
    digits = [int(ch) for ch in candidate if ch.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class PatternRedactor:
    """Replace PII and secret patterns in text with [REDACTED]."""

    def name(self) -> str:
        return "pattern-redactor"

    def redact(self, text: str) -> str:
        for _label, pattern in _PATTERNS:
            text = pattern.sub(_PLACEHOLDER, text)
        text = _CARD_PATTERN.sub(
            lambda match: _PLACEHOLDER if _luhn_valid(match.group(0)) else match.group(0),
            text,
        )
        return text
