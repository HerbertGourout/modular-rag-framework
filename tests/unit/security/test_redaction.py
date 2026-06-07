"""Unit tests for PatternRedactor."""
from __future__ import annotations

from modular_rag.security.redaction.patterns import PatternRedactor


def test_name():
    redactor = PatternRedactor()
    assert redactor.name() == "pattern-redactor"


def test_redacts_email():
    text = "Contact me at john.doe@example.com for details."
    result = PatternRedactor().redact(text)
    assert "john.doe@example.com" not in result
    assert "[REDACTED]" in result


def test_redacts_multiple_emails():
    text = "From: alice@example.org and bob@test.net"
    result = PatternRedactor().redact(text)
    assert "alice@example.org" not in result
    assert "bob@test.net" not in result


def test_redacts_french_phone():
    text = "Appelez le +33 6 12 34 56 78 pour plus d'info."
    result = PatternRedactor().redact(text)
    assert "+33 6 12 34 56 78" not in result
    assert "[REDACTED]" in result


def test_benign_text_unchanged():
    text = "The quick brown fox jumps over the lazy dog."
    result = PatternRedactor().redact(text)
    assert result == text


def test_redacts_api_key_pattern():
    text = "Use key sk-abcdefghijklmnopqrstuvwxyz123456 to authenticate."
    result = PatternRedactor().redact(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result
