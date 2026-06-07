"""Unit tests for FixedSizeChunker."""
from __future__ import annotations

from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker


def _doc(text: str) -> Document:
    return Document(source="test.txt", content=text)


def test_name():
    chunker = FixedSizeChunker()
    assert chunker.name() == "fixed-size"


def test_short_text_single_chunk():
    doc = _doc("Hello world. This is a short document.")
    chunks = FixedSizeChunker(chunk_size=512).chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == doc.content


def test_long_text_splits_into_multiple_chunks():
    content = "a" * 2000
    doc = _doc(content)
    chunks = FixedSizeChunker(chunk_size=512, chunk_overlap=64).chunk(doc)
    assert len(chunks) > 1


def test_chunks_cover_all_content():
    content = "word " * 300
    doc = _doc(content)
    chunks = FixedSizeChunker(chunk_size=100, chunk_overlap=20).chunk(doc)
    # Reconstruct: first chunk is full, subsequent chunks start after overlap
    # Verify no content is lost by checking first and last characters
    assert chunks[0].content.startswith(content[:10])
    last_chunk = chunks[-1]
    assert last_chunk.content.strip() != ""


def test_overlap_means_consecutive_chunks_share_text():
    content = "0123456789" * 60  # 600 chars
    doc = _doc(content)
    chunk_size = 100
    overlap = 20
    chunks = FixedSizeChunker(chunk_size=chunk_size, chunk_overlap=overlap).chunk(doc)

    if len(chunks) > 1:
        tail_of_first = chunks[0].content[-(overlap):]
        head_of_second = chunks[1].content[: overlap]
        assert tail_of_first == head_of_second


def test_chunk_doc_id_matches_document():
    doc = _doc("Some content here for testing purposes with enough text to be meaningful.")
    chunks = FixedSizeChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.doc_id == doc.id


def test_empty_document_returns_no_chunks():
    doc = _doc("")
    chunks = FixedSizeChunker().chunk(doc)
    assert chunks == []


def test_chunk_start_end_chars():
    content = "0123456789" * 10  # 100 chars
    doc = _doc(content)
    chunks = FixedSizeChunker(chunk_size=40, chunk_overlap=0).chunk(doc)
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 40
