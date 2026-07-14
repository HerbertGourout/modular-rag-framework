"""Unit tests for CrossEncoderReranker.

Injects a fake model on `_model` so the tests exercise the reranker's own
logic (pair building, sorting, truncation, rank/score rewriting) without
loading sentence-transformers.
"""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.rerankers.cross_encoder import CrossEncoderReranker


class _FakeCrossEncoder:
    """Returns pre-set scores and records the (query, passage) pairs it saw."""

    def __init__(self, scores: list[float]) -> None:
        self._scores = scores
        self.seen_pairs: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.seen_pairs = list(pairs)
        return self._scores[: len(pairs)]


def _hit(content: str, score: float = 0.5, rank: int = 1) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content)
    return RetrievedChunk(
        chunk=chunk, score=score, rank=rank, retrieval_method=RetrievalMethod.HYBRID
    )


def _reranker(scores: list[float]) -> tuple[CrossEncoderReranker, _FakeCrossEncoder]:
    reranker = CrossEncoderReranker()
    fake = _FakeCrossEncoder(scores)
    reranker._model = fake
    return reranker, fake


def test_empty_input_returns_empty_without_loading_model():
    reranker = CrossEncoderReranker()

    assert reranker.rerank(Query(text="q"), [], k=5) == []
    # No model must have been loaded for the empty short-circuit.
    assert reranker._model is None


def test_model_is_not_loaded_at_init():
    reranker = CrossEncoderReranker()
    assert reranker._model is None


def test_reorders_by_model_score_descending():
    reranker, _ = _reranker(scores=[0.1, 0.9, 0.5])
    hits = [_hit("low"), _hit("high"), _hit("mid")]

    result = reranker.rerank(Query(text="q"), hits, k=3)

    assert [r.chunk.content for r in result] == ["high", "mid", "low"]


def test_respects_k_truncation():
    reranker, _ = _reranker(scores=[0.4, 0.3, 0.2, 0.1])
    hits = [_hit(f"doc {i}") for i in range(4)]

    result = reranker.rerank(Query(text="q"), hits, k=2)

    assert len(result) == 2


def test_ranks_are_sequential_and_scores_come_from_model():
    reranker, _ = _reranker(scores=[0.2, 0.8])
    hits = [_hit("second", score=0.99), _hit("first", score=0.01)]

    result = reranker.rerank(Query(text="q"), hits, k=2)

    assert [r.rank for r in result] == [1, 2]
    assert [r.score for r in result] == [0.8, 0.2]


def test_pairs_are_built_from_query_and_chunk_content():
    reranker, fake = _reranker(scores=[0.5, 0.5])
    hits = [_hit("passage one"), _hit("passage two")]

    reranker.rerank(Query(text="my question"), hits, k=2)

    assert fake.seen_pairs == [
        ("my question", "passage one"),
        ("my question", "passage two"),
    ]


def test_original_chunks_are_not_mutated():
    reranker, _ = _reranker(scores=[0.9])
    original = _hit("doc", score=0.123, rank=7)

    result = reranker.rerank(Query(text="q"), [original], k=1)

    assert original.score == 0.123
    assert original.rank == 7
    assert result[0].score == 0.9
    assert result[0].rank == 1


def test_name_is_stable_identifier():
    assert CrossEncoderReranker().name() == "cross-encoder"
