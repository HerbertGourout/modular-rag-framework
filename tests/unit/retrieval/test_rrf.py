"""Unit tests for Reciprocal Rank Fusion."""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.fusion.rrf import reciprocal_rank_fusion


def _make_retrieved(content: str, rank: int, method: RetrievalMethod = RetrievalMethod.VECTOR) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content)
    return RetrievedChunk(chunk=chunk, score=1.0 / rank, rank=rank, retrieval_method=method)


def test_single_list_preserves_order():
    items = [_make_retrieved(f"doc{i}", i) for i in range(1, 6)]
    result = reciprocal_rank_fusion([items], k=5)
    assert len(result) == 5
    assert result[0].rank == 1


def test_deduplicates_by_chunk_id():
    doc_id = new_id()
    shared_chunk = Chunk(doc_id=doc_id, content="shared document")
    r1 = RetrievedChunk(chunk=shared_chunk, score=0.9, rank=1, retrieval_method=RetrievalMethod.VECTOR)
    r2 = RetrievedChunk(chunk=shared_chunk, score=0.7, rank=2, retrieval_method=RetrievalMethod.BM25)

    unique_chunk = Chunk(doc_id=new_id(), content="unique document")
    r3 = RetrievedChunk(chunk=unique_chunk, score=0.6, rank=1, retrieval_method=RetrievalMethod.BM25)

    result = reciprocal_rank_fusion([[r1, r3], [r2]], k=10)

    ids = [r.chunk.id for r in result]
    assert len(ids) == len(set(ids))  # no duplicates


def test_shared_document_gets_boosted_score():
    doc_id = new_id()
    shared = Chunk(doc_id=doc_id, content="high-relevance document")
    r_vec = RetrievedChunk(chunk=shared, score=0.9, rank=1, retrieval_method=RetrievalMethod.VECTOR)
    r_bm25 = RetrievedChunk(chunk=shared, score=0.8, rank=1, retrieval_method=RetrievalMethod.BM25)

    only_vec_chunk = Chunk(doc_id=new_id(), content="only in vector")
    r_only = RetrievedChunk(chunk=only_vec_chunk, score=0.5, rank=2, retrieval_method=RetrievalMethod.VECTOR)

    result = reciprocal_rank_fusion([[r_vec, r_only], [r_bm25]], k=10)

    # shared doc should rank first (boosted by appearing in both lists)
    assert result[0].chunk.id == shared.id


def test_k_limits_output():
    items = [_make_retrieved(f"doc{i}", i) for i in range(1, 11)]
    result = reciprocal_rank_fusion([items], k=3)
    assert len(result) == 3


def test_empty_lists_return_empty():
    result = reciprocal_rank_fusion([], k=10)
    assert result == []


def test_rrf_scores_are_re_ranked():
    items = [_make_retrieved(f"doc{i}", i) for i in range(1, 6)]
    result = reciprocal_rank_fusion([items], k=5)
    # Ranks should be 1..5 after reranking
    ranks = [r.rank for r in result]
    assert ranks == list(range(1, len(result) + 1))
