"""Characterization tests for eval/scorers/retrieval_metrics.py.

Lot 4 (docs/refactoring-plan.md), Part 2. This module had 0 direct tests
before (only import-line coverage, per the Lot 3 coverage report).
"""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.eval.scorers.retrieval_metrics import (
    compute_retrieval_metrics,
    mrr,
    precision_at_k,
    recall_at_k,
)


def _hits(*ids_in_rank_order: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk=Chunk(id=cid, doc_id=new_id(), content="x"),
            score=1.0,
            rank=i + 1,
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for i, cid in enumerate(ids_in_rank_order)
    ]


def test_recall_at_k_counts_relevant_hits_within_the_top_k_window() -> None:
    retrieved = _hits("a", "b", "c", "d")

    assert recall_at_k(retrieved, relevant_ids={"a", "c"}, k=2) == 0.5  # only "a" is in top 2
    assert recall_at_k(retrieved, relevant_ids={"a", "c"}, k=4) == 1.0


def test_recall_at_k_returns_zero_when_there_are_no_relevant_ids() -> None:
    """Division-by-zero guard: an empty relevant set returns 0.0, not NaN
    or an exception — even though "0 out of 0 relevant found" is arguably
    undefined rather than 0."""
    retrieved = _hits("a", "b")

    assert recall_at_k(retrieved, relevant_ids=set(), k=2) == 0.0


def test_precision_at_k_divides_by_actual_window_size_not_by_k() -> None:
    """When fewer than k chunks were retrieved, precision divides by the
    actual count returned, not by the requested k."""
    retrieved = _hits("a", "b")

    assert precision_at_k(retrieved, relevant_ids={"a"}, k=10) == 0.5


def test_precision_at_k_returns_zero_for_an_empty_retrieved_list() -> None:
    assert precision_at_k([], relevant_ids={"a"}, k=5) == 0.0


def test_mrr_is_the_reciprocal_rank_of_the_first_relevant_hit() -> None:
    retrieved = _hits("x", "y", "a", "z")

    assert mrr(retrieved, relevant_ids={"a"}) == 1 / 3


def test_mrr_returns_zero_when_nothing_relevant_was_retrieved() -> None:
    retrieved = _hits("x", "y")

    assert mrr(retrieved, relevant_ids={"a"}) == 0.0


def test_compute_retrieval_metrics_aggregates_all_three_and_leaves_others_none() -> None:
    retrieved = _hits("a", "b", "c")

    metrics = compute_retrieval_metrics(retrieved, relevant_ids={"a"}, k=3)

    assert metrics.recall_at_k == 1.0
    assert metrics.precision_at_k == 1 / 3
    assert metrics.mrr == 1.0
    assert metrics.ndcg is None  # not computed by this function
    assert metrics.answer_relevance is None  # answer-side metric, out of scope here
