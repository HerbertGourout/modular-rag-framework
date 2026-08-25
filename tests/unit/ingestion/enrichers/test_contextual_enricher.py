"""Unit tests for ingestion/enrichers/contextual_enricher.py."""
from __future__ import annotations

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.ingestion.enrichers.contextual_enricher import ContextualEnricher


def test_enrich_prefixes_embedding_text_with_the_document_filename() -> None:
    document = Document(source="reports/q3.pdf", content="irrelevant", metadata={"filename": "q3.pdf"})
    chunk = Chunk(doc_id=document.id, content="Revenue grew 12% year over year.")

    [enriched] = ContextualEnricher().enrich(document, [chunk])

    assert enriched.embedding_text == "Document: q3.pdf\n\nRevenue grew 12% year over year."


def test_enrich_falls_back_to_source_when_no_filename_metadata_is_set() -> None:
    document = Document(source="https://example.com/page", content="irrelevant")
    chunk = Chunk(doc_id=document.id, content="hello world")

    [enriched] = ContextualEnricher().enrich(document, [chunk])

    assert enriched.embedding_text == "Document: https://example.com/page\n\nhello world"


def test_enrich_never_mutates_chunk_content() -> None:
    """Citations and /retrieve read `content` directly -- the context prefix
    must only ever land in `embedding_text`."""
    document = Document(source="doc.txt", content="irrelevant", metadata={"filename": "doc.txt"})
    chunk = Chunk(doc_id=document.id, content="original text")

    [enriched] = ContextualEnricher().enrich(document, [chunk])

    assert enriched.content == "original text"


def test_enrich_preserves_chunk_identity_and_other_fields() -> None:
    document = Document(source="doc.txt", content="irrelevant", metadata={"filename": "doc.txt"})
    chunk = Chunk(doc_id=document.id, content="text", tenant_id="acme", page=3)

    [enriched] = ContextualEnricher().enrich(document, [chunk])

    assert enriched.id == chunk.id
    assert enriched.tenant_id == "acme"
    assert enriched.page == 3


def test_enrich_handles_multiple_chunks_independently() -> None:
    document = Document(source="doc.txt", content="irrelevant", metadata={"filename": "doc.txt"})
    chunks = [
        Chunk(doc_id=document.id, content="first"),
        Chunk(doc_id=document.id, content="second"),
    ]

    enriched = ContextualEnricher().enrich(document, chunks)

    assert [c.embedding_text for c in enriched] == [
        "Document: doc.txt\n\nfirst",
        "Document: doc.txt\n\nsecond",
    ]


def test_enrich_handles_an_empty_chunk_list() -> None:
    document = Document(source="doc.txt", content="irrelevant")

    assert ContextualEnricher().enrich(document, []) == []
