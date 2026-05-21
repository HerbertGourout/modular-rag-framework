"""Contract conformance tests for Chunker implementations."""
from __future__ import annotations

import pytest

from modular_rag.contracts.chunking import Chunker
from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers.adaptive import AdaptiveChunker
from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker


def _sample_doc() -> Document:
    return Document(source="sample.txt", content="This is a sample document. " * 50)


CHUNKERS = [
    FixedSizeChunker(),
    AdaptiveChunker(),
]


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_implements_chunker_protocol(chunker):
    assert isinstance(chunker, Chunker)


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_name_returns_non_empty_string(chunker):
    name = chunker.name()
    assert isinstance(name, str)
    assert len(name) > 0


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_chunk_returns_list(chunker):
    doc = _sample_doc()
    result = chunker.chunk(doc)
    assert isinstance(result, list)


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_chunk_returns_chunk_objects(chunker):
    from modular_rag.core.models.chunk import Chunk

    doc = _sample_doc()
    result = chunker.chunk(doc)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, Chunk)


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_chunk_doc_id_propagated(chunker):
    doc = _sample_doc()
    result = chunker.chunk(doc)
    for chunk in result:
        assert chunk.doc_id == doc.id


@pytest.mark.parametrize("chunker", CHUNKERS, ids=lambda c: c.name())
def test_chunk_content_non_empty(chunker):
    doc = _sample_doc()
    result = chunker.chunk(doc)
    for chunk in result:
        assert chunk.content.strip() != ""
