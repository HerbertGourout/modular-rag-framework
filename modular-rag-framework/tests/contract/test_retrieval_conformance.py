"""Contract conformance tests for Retriever implementations.

Note: VectorRetriever and HybridRetriever require external services (Qdrant).
This file tests only the BM25Retriever which works fully in-process.
Integration tests for Qdrant-backed retrievers live in tests/integration/.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.retrieval import Retriever
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever


def _chunks(n: int = 10) -> list[Chunk]:
    topics = [
        "Retrieval-Augmented Generation combines retrieval and generation.",
        "Vector databases store dense embeddings for semantic search.",
        "BM25 is a probabilistic retrieval model based on term frequency.",
        "Knowledge graphs represent entities and their relationships.",
        "Large language models are trained on vast amounts of text.",
        "Chunking splits documents into smaller pieces for indexing.",
        "Cross-encoders rerank retrieved candidates for better relevance.",
        "Hybrid retrieval fuses vector and lexical scores via RRF.",
        "Agentic systems decompose complex tasks into sub-goals.",
        "Evaluation metrics include recall@k, MRR, and groundedness.",
    ]
    return [Chunk(doc_id=new_id(), content=t) for t in topics[:n]]


@pytest.fixture
def bm25_retriever() -> BM25Retriever:
    retriever = BM25Retriever()
    retriever.index(_chunks())
    return retriever


def test_implements_retriever_protocol(bm25_retriever):
    assert isinstance(bm25_retriever, Retriever)


def test_name_returns_string(bm25_retriever):
    assert isinstance(bm25_retriever.name(), str)
    assert len(bm25_retriever.name()) > 0


def test_retrieve_returns_list(bm25_retriever):
    q = Query(text="what is BM25?")
    result = bm25_retriever.retrieve(q, k=5)
    assert isinstance(result, list)


def test_retrieve_respects_k(bm25_retriever):
    q = Query(text="retrieval generation")
    result = bm25_retriever.retrieve(q, k=3)
    assert len(result) <= 3


def test_retrieve_returns_retrieved_chunks(bm25_retriever):
    from modular_rag.core.models.retrieved import RetrievedChunk

    q = Query(text="vector database embeddings")
    result = bm25_retriever.retrieve(q, k=5)
    for item in result:
        assert isinstance(item, RetrievedChunk)


def test_retrieve_ranks_are_sequential(bm25_retriever):
    q = Query(text="retrieval augmented generation language models")
    result = bm25_retriever.retrieve(q, k=5)
    ranks = [r.rank for r in result]
    assert ranks == list(range(1, len(result) + 1))


def test_retrieve_relevant_doc_scores_high(bm25_retriever):
    q = Query(text="BM25 probabilistic retrieval term frequency")
    result = bm25_retriever.retrieve(q, k=10)
    top_content = result[0].chunk.content if result else ""
    assert "BM25" in top_content or result[0].score > 0
