"""Unit tests for HybridRetriever's fusion-weight wiring.

Uses fake sub-retrievers injected on `_vector`/`_bm25` so the test exercises
HybridRetriever's own logic (weight pass-through to RRF) without needing Qdrant.
"""
from __future__ import annotations

import pytest

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.retrievers.hybrid import HybridRetriever


class _FakeRetriever:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self._hits[:k]


class _FailingRetriever:
    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        raise RuntimeError("source unavailable")


def _hit(content: str, method: RetrievalMethod) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content)
    return RetrievedChunk(chunk=chunk, score=0.5, rank=1, retrieval_method=method)


def test_default_weights_favor_neither_source():
    retriever = HybridRetriever()
    vector_only = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([vector_only])
    retriever._bm25 = _FakeRetriever([bm25_only])

    result = retriever.retrieve(Query(text="q"), k=10)

    ids = {r.chunk.id for r in result}
    assert ids == {vector_only.chunk.id, bm25_only.chunk.id}


def test_vector_weight_dominates_when_bm25_weight_is_zero():
    retriever = HybridRetriever(vector_weight=1.0, bm25_weight=0.0)
    vector_only = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([vector_only])
    retriever._bm25 = _FakeRetriever([bm25_only])

    # Both tie at rank 1 in their own list; with bm25_weight=0 the vector-sourced
    # item must win the single top-1 slot.
    result = retriever.retrieve(Query(text="q"), k=1)

    assert [r.chunk.id for r in result] == [vector_only.chunk.id]


def test_higher_weight_wins_a_tie():
    retriever = HybridRetriever(vector_weight=0.9, bm25_weight=0.1)
    doc_a = _hit("doc a", RetrievalMethod.VECTOR)
    doc_b = _hit("doc b", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([doc_a])
    retriever._bm25 = _FakeRetriever([doc_b])

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result[0].chunk.id == doc_a.chunk.id


def test_hybrid_retriever_falls_back_when_vector_source_is_unavailable():
    retriever = HybridRetriever()
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FailingRetriever()
    retriever._bm25 = _FakeRetriever([bm25_only])

    result = retriever.retrieve(Query(text="q"), k=10)

    assert [r.chunk.id for r in result] == [bm25_only.chunk.id]
    assert result[0].retrieval_method == RetrievalMethod.BM25


def test_hybrid_retriever_returns_empty_list_without_raising_when_both_sources_fail():
    """Lot 4 (docs/refactoring-plan.md §2, 'Resilience'): `_safe_retrieve` catches
    *any* exception from either source and logs a warning, never re-raising. If
    both vector and BM25 fail, `retrieve()` silently returns `[]` — RAGEngine
    then proceeds to generation with zero context and no error signal
    distinguishing "both retrieval sources are down" from "no relevant
    documents exist." Characterized, not fixed here.
    """
    retriever = HybridRetriever()
    retriever._vector = _FailingRetriever()
    retriever._bm25 = _FailingRetriever()

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result == []


def test_hybrid_retriever_mutates_rank_and_method_on_a_nominally_frozen_retrievedchunk():
    """`RetrievedChunk.model_config = {"frozen": True}` — normal attribute
    assignment (`chunk.rank = 5`) raises a pydantic ValidationError. HybridRetriever
    bypasses that via `object.__setattr__` to renumber rank/retrieval_method after
    fusion. This proves "frozen" is not actually enforced for chunks that pass
    through hybrid retrieval — a design quirk, not endorsed, characterized only.
    """
    retriever = HybridRetriever()
    vector_hit = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_hit = _hit("bm25 document", RetrievalMethod.BM25)
    original_rank = vector_hit.rank
    retriever._vector = _FakeRetriever([vector_hit])
    retriever._bm25 = _FakeRetriever([bm25_hit])

    with pytest.raises(Exception, match="frozen|immutable"):
        vector_hit.rank = 99  # sanity check: the model really is nominally frozen

    result = retriever.retrieve(Query(text="q"), k=10)

    # At least one fused result has been renumbered away from its pre-fusion rank
    # via object.__setattr__, despite the model's frozen config.
    assert any(r.rank != original_rank for r in result) or len(result) <= 1
    assert all(r.retrieval_method == RetrievalMethod.HYBRID for r in result)
