"""Unit tests for Reciprocal Rank Fusion."""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.fusion.rrf import reciprocal_rank_fusion


def _make_retrieved(
    content: str, rank: int, method: RetrievalMethod = RetrievalMethod.VECTOR
) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content)
    return RetrievedChunk(chunk=chunk, score=1.0 / rank, rank=rank, retrieval_method=method)


def _rc(chunk: Chunk, score: float, rank: int, method: RetrievalMethod) -> RetrievedChunk:
    return RetrievedChunk(chunk=chunk, score=score, rank=rank, retrieval_method=method)


def test_single_list_preserves_order():
    items = [_make_retrieved(f"doc{i}", i) for i in range(1, 6)]
    result = reciprocal_rank_fusion([items], k=5)
    assert len(result) == 5
    assert result[0].rank == 1


def test_deduplicates_by_chunk_id():
    doc_id = new_id()
    shared_chunk = Chunk(doc_id=doc_id, content="shared document")
    r1 = _rc(shared_chunk, score=0.9, rank=1, method=RetrievalMethod.VECTOR)
    r2 = _rc(shared_chunk, score=0.7, rank=2, method=RetrievalMethod.BM25)

    unique_chunk = Chunk(doc_id=new_id(), content="unique document")
    r3 = _rc(unique_chunk, score=0.6, rank=1, method=RetrievalMethod.BM25)

    result = reciprocal_rank_fusion([[r1, r3], [r2]], k=10)

    ids = [r.chunk.id for r in result]
    assert len(ids) == len(set(ids))  # no duplicates


def test_shared_document_gets_boosted_score():
    doc_id = new_id()
    shared = Chunk(doc_id=doc_id, content="high-relevance document")
    r_vec = RetrievedChunk(chunk=shared, score=0.9, rank=1, retrieval_method=RetrievalMethod.VECTOR)
    r_bm25 = RetrievedChunk(chunk=shared, score=0.8, rank=1, retrieval_method=RetrievalMethod.BM25)

    only_vec_chunk = Chunk(doc_id=new_id(), content="only in vector")
    r_only = _rc(only_vec_chunk, score=0.5, rank=2, method=RetrievalMethod.VECTOR)

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


def test_default_weights_match_unweighted_fusion():
    doc_id = new_id()
    shared = Chunk(doc_id=doc_id, content="shared document")
    r_vec = RetrievedChunk(chunk=shared, score=0.9, rank=1, retrieval_method=RetrievalMethod.VECTOR)
    r_bm25 = RetrievedChunk(chunk=shared, score=0.8, rank=1, retrieval_method=RetrievalMethod.BM25)

    unweighted = reciprocal_rank_fusion([[r_vec], [r_bm25]], k=10)
    explicitly_uniform = reciprocal_rank_fusion([[r_vec], [r_bm25]], k=10, weights=[1.0, 1.0])

    assert [r.chunk.id for r in unweighted] == [r.chunk.id for r in explicitly_uniform]


def test_zero_weight_loses_tie_to_weighted_list():
    only_in_vector = Chunk(doc_id=new_id(), content="vector-only document")
    only_in_bm25 = Chunk(doc_id=new_id(), content="bm25-only document")
    r_vec = _rc(only_in_vector, score=0.9, rank=1, method=RetrievalMethod.VECTOR)
    r_bm25 = _rc(only_in_bm25, score=0.9, rank=1, method=RetrievalMethod.BM25)

    # Both tie at rank 1 in their own list; zeroing BM25's weight means it contributes
    # no score, so the vector-sourced item must win the single top-1 slot.
    result = reciprocal_rank_fusion([[r_vec], [r_bm25]], k=1, weights=[1.0, 0.0])

    assert result[0].chunk.id == only_in_vector.id


def test_higher_weight_breaks_ties_in_its_favor():
    doc_a = Chunk(doc_id=new_id(), content="doc a")
    doc_b = Chunk(doc_id=new_id(), content="doc b")
    # Both docs tie at rank 1 in their respective single-source lists.
    r_a_vector_only = _rc(doc_a, score=0.5, rank=1, method=RetrievalMethod.VECTOR)
    r_b_bm25_only = _rc(doc_b, score=0.5, rank=1, method=RetrievalMethod.BM25)

    result = reciprocal_rank_fusion(
        [[r_a_vector_only], [r_b_bm25_only]], k=10, weights=[0.9, 0.1]
    )

    assert result[0].chunk.id == doc_a.id
