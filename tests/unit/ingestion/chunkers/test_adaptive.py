"""Unit tests for AdaptiveChunker (token-based sizing + split-then-merge).

Defaults per arXiv:2604.12047; min-fragment merge per arXiv:2603.25333.
"""
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


def test_sota_defaults():
    # Defaults per arXiv:2604.12047 + min-fragment merge per arXiv:2603.25333.
    chunker = AdaptiveChunker()
    assert chunker.chunk_size == 512
    assert chunker.chunk_overlap == 128
    assert chunker.min_chunk_tokens == 100


def test_structured_doc_splits_on_headings():
    # Disable the merge pass to observe raw structural splitting.
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker(max_chunk_size=512, min_chunk_tokens=0).chunk(doc)
    assert len(chunks) >= 3  # at least one chunk per section


def test_small_fragments_merged_by_default():
    # Each section is ~15 tokens (< default min_chunk_tokens=100), so the
    # split-then-merge pass (arXiv:2603.25333) fuses them into one chunk.
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    assert len(chunks) == 1


def test_min_chunk_tokens_configurable():
    doc = _doc(STRUCTURED_DOC)
    no_merge = AdaptiveChunker(min_chunk_tokens=0).chunk(doc)
    aggressive = AdaptiveChunker(min_chunk_tokens=1000).chunk(doc)
    assert len(no_merge) >= 3
    assert len(aggressive) == 1


def test_chunk_doc_id_matches():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.doc_id == doc.id


def test_flat_text_still_produces_chunks():
    flat = "This is a flat document. " * 100  # 500 tokens
    doc = _doc(flat)
    chunks = AdaptiveChunker(max_chunk_size=200).chunk(doc)
    assert len(chunks) >= 1


def test_oversized_section_is_token_windowed():
    flat = "This is a flat document. " * 100  # 500 tokens, single section
    doc = _doc(flat)
    chunks = AdaptiveChunker(max_chunk_size=200, chunk_overlap=0, min_chunk_tokens=0).chunk(doc)
    assert len(chunks) > 1
    assert all(chunk.token_estimate <= 200 for chunk in chunks)


def test_empty_document_returns_no_chunks():
    doc = _doc("")
    chunks = AdaptiveChunker().chunk(doc)
    assert chunks == []


def test_chunk_content_non_empty():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.content.strip() != ""


def test_offsets_are_faithful_to_source():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker(min_chunk_tokens=0).chunk(doc)
    for chunk in chunks:
        assert doc.content[chunk.start_char : chunk.end_char] == chunk.content


def test_document_tenant_id_propagates_to_every_chunk():
    """Tenant-aware ingestion depends on this: test-specialist review found
    deleting this propagation broke no test — closes that gap."""
    doc = Document(source="test.md", content=STRUCTURED_DOC, tenant_id="acme-corp")
    chunks = AdaptiveChunker().chunk(doc)
    assert len(chunks) > 0
    assert all(c.tenant_id == "acme-corp" for c in chunks)


def test_document_with_no_tenant_id_yields_chunks_with_none():
    doc = _doc(STRUCTURED_DOC)
    chunks = AdaptiveChunker().chunk(doc)
    assert all(c.tenant_id is None for c in chunks)
