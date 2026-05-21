"""Unit tests for TextNormalizer."""
from __future__ import annotations

from modular_rag.core.models.document import Document
from modular_rag.ingestion.normalizers.text_normalizer import TextNormalizer


def _doc(text: str) -> Document:
    return Document(source="test.txt", content=text)


def test_collapses_excessive_newlines():
    doc = _doc("Line one.\n\n\n\n\nLine two.")
    result = TextNormalizer.normalize(doc)
    assert "\n\n\n" not in result.content
    assert "Line one." in result.content
    assert "Line two." in result.content


def test_collapses_excessive_spaces():
    doc = _doc("word    multiple    spaces")
    result = TextNormalizer.normalize(doc)
    assert "    " not in result.content
    assert "word" in result.content


def test_strips_leading_trailing_whitespace():
    doc = _doc("   \n  hello world  \n  ")
    result = TextNormalizer.normalize(doc)
    assert result.content == result.content.strip()


def test_preserves_content_semantics():
    text = "The quick brown fox."
    doc = _doc(text)
    result = TextNormalizer.normalize(doc)
    assert "quick brown fox" in result.content


def test_normalizer_returns_document():
    doc = _doc("simple text")
    result = TextNormalizer.normalize(doc)
    assert isinstance(result, Document)
    assert result.source == doc.source
