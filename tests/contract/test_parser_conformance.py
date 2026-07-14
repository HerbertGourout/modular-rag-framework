"""Contract conformance tests for Parser implementations."""
from __future__ import annotations

import pytest

from modular_rag.contracts.parsing import Parser
from modular_rag.core.models.document import Document
from modular_rag.ingestion.parsers.docx_parser import DocxParser
from modular_rag.ingestion.parsers.html_parser import HTMLParser
from modular_rag.ingestion.parsers.pdf_parser import PDFParser
from modular_rag.ingestion.parsers.text_parser import TextParser

PARSERS = [TextParser(), PDFParser(), DocxParser(), HTMLParser()]


@pytest.mark.parametrize("parser", PARSERS, ids=lambda p: type(p).__name__)
def test_implements_parser_protocol(parser):
    assert isinstance(parser, Parser)


@pytest.mark.parametrize("parser", PARSERS, ids=lambda p: type(p).__name__)
def test_supports_rejects_unknown_extension(parser):
    assert parser.supports("sample.unknownext") is False


def test_text_parser_parses_sample(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("Hello world.", encoding="utf-8")
    doc = TextParser().parse(path)
    assert isinstance(doc, Document)
    assert doc.content == "Hello world."


def test_html_parser_parses_sample(tmp_path):
    path = tmp_path / "sample.html"
    path.write_text(
        "<html><head><title>T</title></head><body><p>Hello</p></body></html>",
        encoding="utf-8",
    )
    doc = HTMLParser().parse(path)
    assert isinstance(doc, Document)
    assert "Hello" in doc.content
    assert doc.metadata.get("title") == "T"


def test_docx_parser_parses_sample(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "sample.docx"
    word_doc = docx.Document()
    word_doc.add_paragraph("Hello world.")
    word_doc.save(str(path))

    doc = DocxParser().parse(path)
    assert isinstance(doc, Document)
    assert "Hello world." in doc.content


def test_pdf_parser_parses_sample(tmp_path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "sample.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Hello world.")
    pdf.save(str(path))
    pdf.close()

    doc = PDFParser().parse(path)
    assert isinstance(doc, Document)
    assert "Hello world." in doc.content
