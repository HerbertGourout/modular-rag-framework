"""Unit tests for FixedSizeChunker (token-based sizing per arXiv:2604.12047)."""
from __future__ import annotations

from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker


def _doc(text: str) -> Document:
    return Document(source="test.txt", content=text)


def _words(n: int) -> str:
    """A document of ``n`` distinct whitespace tokens (== ``n`` default tokens)."""
    return " ".join(f"tok{i}" for i in range(n))


def test_name():
    chunker = FixedSizeChunker()
    assert chunker.name() == "fixed-size"


def test_sota_defaults():
    # Defaults per arXiv:2604.12047 — 512 tokens, 128-token (25%) overlap.
    chunker = FixedSizeChunker()
    assert chunker.chunk_size == 512
    assert chunker.chunk_overlap == 128


def test_short_text_single_chunk():
    doc = _doc("Hello world. This is a short document.")
    chunks = FixedSizeChunker(chunk_size=512).chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == doc.content


def test_long_text_splits_into_multiple_chunks():
    doc = _doc(_words(800))  # 800 tokens > 512
    chunks = FixedSizeChunker(chunk_size=512, chunk_overlap=128).chunk(doc)
    assert len(chunks) > 1


def test_token_based_sizing_respects_chunk_size():
    doc = _doc(_words(300))
    chunks = FixedSizeChunker(chunk_size=100, chunk_overlap=20).chunk(doc)
    # With the whitespace counter, token_estimate == word count <= chunk_size.
    assert all(chunk.token_estimate <= 100 for chunk in chunks)


def test_chunks_cover_all_content():
    content = "word " * 300
    doc = _doc(content)
    chunks = FixedSizeChunker(chunk_size=100, chunk_overlap=20).chunk(doc)
    assert chunks[0].content.startswith(content[:10])
    assert chunks[-1].content.strip() != ""


def test_overlap_means_consecutive_chunks_share_tokens():
    doc = _doc(_words(200))
    overlap = 10
    chunks = FixedSizeChunker(chunk_size=50, chunk_overlap=overlap).chunk(doc)
    assert len(chunks) > 1
    tail = chunks[0].content.split()[-overlap:]
    head = chunks[1].content.split()[:overlap]
    assert tail == head


def test_zero_overlap_no_shared_tokens():
    doc = _doc(_words(120))
    chunks = FixedSizeChunker(chunk_size=40, chunk_overlap=0).chunk(doc)
    assert len(chunks) == 3
    all_tokens = [t for chunk in chunks for t in chunk.content.split()]
    assert len(all_tokens) == 120  # no duplication with zero overlap


def test_custom_token_counter_is_used():
    # A character-based counter makes windows much smaller than the word-based default.
    doc = _doc(_words(50))
    char_counted = FixedSizeChunker(chunk_size=20, chunk_overlap=0, token_counter=len).chunk(doc)
    word_counted = FixedSizeChunker(chunk_size=20, chunk_overlap=0).chunk(doc)
    assert len(char_counted) > len(word_counted)


def test_chunk_doc_id_matches_document():
    doc = _doc("Some content here for testing purposes with enough text to be meaningful.")
    chunks = FixedSizeChunker().chunk(doc)
    for chunk in chunks:
        assert chunk.doc_id == doc.id


def test_empty_document_returns_no_chunks():
    doc = _doc("")
    chunks = FixedSizeChunker().chunk(doc)
    assert chunks == []


def test_whitespace_only_document_returns_no_chunks():
    doc = _doc("   \n\n  \t ")
    chunks = FixedSizeChunker().chunk(doc)
    assert chunks == []


def test_chunk_start_end_chars_are_token_bounded():
    doc = _doc("alpha beta gamma delta")
    chunks = FixedSizeChunker(chunk_size=2, chunk_overlap=0).chunk(doc)
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 10  # "alpha beta"
    assert chunks[0].content == "alpha beta"


def test_offsets_are_faithful_to_source():
    doc = _doc(_words(200))
    chunks = FixedSizeChunker(chunk_size=50, chunk_overlap=10).chunk(doc)
    for chunk in chunks:
        assert doc.content[chunk.start_char : chunk.end_char] == chunk.content
