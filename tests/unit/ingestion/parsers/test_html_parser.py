"""Unit tests for HTMLParser."""
from __future__ import annotations

from modular_rag.core.models.document import Document
from modular_rag.ingestion.parsers.html_parser import HTMLParser


def test_supports_html_extensions():
    parser = HTMLParser()
    assert parser.supports("page.html") is True
    assert parser.supports("page.HTM") is True
    assert parser.supports("page.txt") is False


def test_parse_returns_document(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><title>My Page</title></head>"
        "<body><h1>Heading</h1><p>Body text.</p></body></html>",
        encoding="utf-8",
    )

    doc = HTMLParser().parse(path)

    assert isinstance(doc, Document)
    assert doc.source == str(path)
    assert doc.mime_type == "text/html"
    assert "Heading" in doc.content
    assert "Body text." in doc.content
    assert doc.metadata["title"] == "My Page"


def test_parse_strips_script_and_style_tags(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><body>"
        "<script>console.log('should not appear');</script>"
        "<style>body { color: red; }</style>"
        "<p>Visible text.</p>"
        "</body></html>",
        encoding="utf-8",
    )

    doc = HTMLParser().parse(path)

    assert "should not appear" not in doc.content
    assert "color: red" not in doc.content
    assert "Visible text." in doc.content


def test_parse_without_title_omits_metadata_key(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("<html><body><p>No title here.</p></body></html>", encoding="utf-8")

    doc = HTMLParser().parse(path)

    assert "title" not in doc.metadata
