"""Unit tests for DocxParser."""
from __future__ import annotations

import pytest

from modular_rag.core.models.document import Document
from modular_rag.ingestion.parsers.docx_parser import DocxParser

docx = pytest.importorskip("docx")


def _write_docx(path, paragraphs: list[str]) -> None:
    word_doc = docx.Document()
    for text in paragraphs:
        word_doc.add_paragraph(text)
    word_doc.save(str(path))


def test_supports_docx_extension():
    parser = DocxParser()
    assert parser.supports("report.docx") is True
    assert parser.supports("report.DOCX") is True
    assert parser.supports("report.pdf") is False


def test_parse_returns_document(tmp_path):
    path = tmp_path / "report.docx"
    _write_docx(path, ["First paragraph.", "Second paragraph."])

    doc = DocxParser().parse(path)

    assert isinstance(doc, Document)
    assert doc.source == str(path)
    assert doc.mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "First paragraph." in doc.content
    assert "Second paragraph." in doc.content


def test_parse_skips_empty_paragraphs(tmp_path):
    path = tmp_path / "report.docx"
    _write_docx(path, ["Real content.", "", "   "])

    doc = DocxParser().parse(path)

    assert doc.metadata["paragraph_count"] == 1


def test_parse_empty_document_returns_empty_content(tmp_path):
    path = tmp_path / "empty.docx"
    _write_docx(path, [])

    doc = DocxParser().parse(path)

    assert doc.content == ""
    assert doc.metadata["paragraph_count"] == 0
