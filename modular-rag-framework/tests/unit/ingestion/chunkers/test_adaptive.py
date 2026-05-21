"""Unit tests for AdaptiveChunker."""
from __future__ import annotations

from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker


def _doc(text: str) -> Document:
    return Document(source="test.md", content=text)


STRUCTURED_DOC = """\
# Introduction

This section introduces the concept.
It has multiple sentences that form a paragraph.

## Background

The background covers related work.
Several papers have discussed this topic.

## Method

Our method builds on top of prior work.
We use a novel approach with three steps.
"""


def test_name():
    chunker = AdaptiveChunker()
    assert chunker.name() == "adaptive"


def test_structured_doc_splits_on_headings():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker(max_chunk_size=512).chunk(doc)
    assert len(chunks) >= 3  # at least one chunk per section


def test_chunk_doc_id_matches():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.doc_id == doc.id


def test_flat_text_still_produces_chunks():
    flat = "This is a flat document. " * 100
    doc = _doc(flat)
    chunks = AdaptiveChunker(max_chunk_size=200).chunk(doc)
    assert len(chunks) >= 1


def test_empty_document_returns_no_chunks():
    doc = _doc("")
    chunks = AdaptiveChunker().chunk(doc)
    assert chunks == []


def test_chunk_content_non_empty():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.content.strip() != ""
