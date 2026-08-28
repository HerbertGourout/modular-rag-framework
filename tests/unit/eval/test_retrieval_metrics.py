"""Characterization tests for eval/scorers/retrieval_metrics.py.

Lot 4 (docs/refactoring-plan.md), Part 2. This module had 0 direct tests
before (only import-line coverage, per the Lot 3 coverage report).

Batch 13 (external plan — "Offline benchmark"): every function's signature
was widened from `list[RetrievedChunk]` to a plain, ordered `list[str]` of
chunk ids (zero real callers existed anywhere in `src/` before this change,
confirmed by grep) so a benchmark can score directly off
`Answer.citations[*].chunk_id` without needing `AnswerEngine` to expose raw
`RetrievedChunk` objects — see the module's own docstring. This file's tests
were rewritten to match, not merely extended.
"""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.eval.scorers.retrieval_metrics import (
    compute_retrieval_metrics,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def _rc(chunk_id: str, rank: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(id=chunk_id, doc_id="d", content="x"),
        score=1.0,
        rank=rank,
        retrieval_method=RetrievalMethod.VECTOR,
    )


def test_recall_at_k_counts_relevant_hits_within_the_top_k_window() -> None:
    retrieved = ["a", "b", "c", "d"]

    assert recall_at_k(retrieved, relevant_ids={"a", "c"}, k=2) == 0.5  # only "a" is in top 2
    assert recall_at_k(retrieved, relevant_ids={"a", "c"}, k=4) == 1.0


def test_recall_at_k_returns_zero_when_there_are_no_relevant_ids() -> None:
    """Division-by-zero guard: an empty relevant set returns 0.0, not NaN
    or an exception — even though "0 out of 0 relevant found" is arguably
    undefined rather than 0."""
    assert recall_at_k(["a", "b"], relevant_ids=set(), k=2) == 0.0


def test_precision_at_k_divides_by_actual_window_size_not_by_k() -> None:
    """When fewer than k chunks were retrieved, precision divides by the
    actual count returned, not by the requested k."""
    assert precision_at_k(["a", "b"], relevant_ids={"a"}, k=10) == 0.5


def test_precision_at_k_returns_zero_for_an_empty_retrieved_list() -> None:
    assert precision_at_k([], relevant_ids={"a"}, k=5) == 0.0


def test_mrr_is_the_reciprocal_rank_of_the_first_relevant_hit() -> None:
    assert mrr(["x", "y", "a", "z"], relevant_ids={"a"}) == 1 / 3


def test_mrr_returns_zero_when_nothing_relevant_was_retrieved() -> None:
    assert mrr(["x", "y"], relevant_ids={"a"}) == 0.0


def test_ndcg_at_k_is_one_for_a_perfectly_ordered_result() -> None:
    """All relevant ids ranked first -> the actual ranking equals the ideal
    ranking -> NDCG@k == 1.0 exactly."""
    assert ndcg_at_k(["a", "b", "x", "y"], relevant_ids={"a", "b"}, k=4) == 1.0


def test_ndcg_at_k_penalizes_relevant_hits_ranked_lower() -> None:
    """One relevant id at rank 1, matching the ideal ranking for k=1 ->
    NDCG@1 == 1.0 regardless of what's outside the window; but pushing the
    only relevant id to rank 2 instead of rank 1 must score strictly lower
    than the ideal at k=2."""
    ideal = ndcg_at_k(["a", "x", "y"], relevant_ids={"a"}, k=2)
    delayed = ndcg_at_k(["x", "a", "y"], relevant_ids={"a"}, k=2)

    assert ideal == 1.0
    assert 0.0 < delayed < ideal


def test_ndcg_at_k_returns_zero_when_nothing_relevant_was_retrieved() -> None:
    assert ndcg_at_k(["x", "y"], relevant_ids={"a"}, k=2) == 0.0


def test_ndcg_at_k_returns_zero_for_an_empty_relevant_set() -> None:
    assert ndcg_at_k(["x", "y"], relevant_ids=set(), k=2) == 0.0


def test_compute_retrieval_metrics_aggregates_all_four_and_leaves_others_none() -> None:
    metrics = compute_retrieval_metrics(["a", "b", "c"], relevant_ids={"a"}, k=3)

    assert metrics.recall_at_k == 1.0
    assert metrics.precision_at_k == 1 / 3
    assert metrics.mrr == 1.0
    assert metrics.ndcg == 1.0  # "a" at rank 1 is already the ideal ordering
    assert metrics.answer_relevance is None  # answer-side metric, out of scope here


# ---------------------------------------------------------------------------
# Codex review (pass 1, MEDIUM-003): duplicate retrieved ids must never
# inflate NDCG past 1.0.
# ---------------------------------------------------------------------------


def test_ndcg_at_k_bounds_duplicate_relevant_ids_to_a_single_gain() -> None:
    """Exact reproduction from the review's own evidence: before the fix,
    ndcg_at_k(["a", "a"], {"a"}, 2) returned ~1.63 -- impossible for a metric
    that must stay in [0, 1]."""
    result = ndcg_at_k(["a", "a"], relevant_ids={"a"}, k=2)

    assert result == 1.0
    assert 0.0 <= result <= 1.0


def test_ndcg_at_k_stays_bounded_with_duplicates_mixed_with_other_ids() -> None:
    result = ndcg_at_k(["a", "a", "a", "b"], relevant_ids={"a", "b"}, k=4)

    assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Codex review (pass 1, HIGH-002): every function must still accept the
# historical `list[RetrievedChunk]` shape, not just the newer `list[str]` one.
# ---------------------------------------------------------------------------


def test_recall_at_k_accepts_the_historical_retrieved_chunk_shape() -> None:
    retrieved = [_rc("a", 1), _rc("b", 2)]

    assert recall_at_k(retrieved, relevant_ids={"a"}, k=2) == 1.0


def test_precision_at_k_accepts_the_historical_retrieved_chunk_shape() -> None:
    retrieved = [_rc("a", 1), _rc("b", 2)]

    assert precision_at_k(retrieved, relevant_ids={"a"}, k=2) == 0.5


def test_mrr_accepts_the_historical_retrieved_chunk_shape() -> None:
    retrieved = [_rc("x", 1), _rc("a", 2)]

    assert mrr(retrieved, relevant_ids={"a"}) == 0.5


def test_ndcg_at_k_accepts_the_historical_retrieved_chunk_shape() -> None:
    retrieved = [_rc("a", 1), _rc("b", 2)]

    assert ndcg_at_k(retrieved, relevant_ids={"a"}, k=2) == 1.0


def test_compute_retrieval_metrics_accepts_the_historical_retrieved_chunk_shape() -> None:
    retrieved = [_rc("a", 1), _rc("b", 2)]

    metrics = compute_retrieval_metrics(retrieved, relevant_ids={"a"}, k=2)

    assert metrics.recall_at_k == 1.0
    assert metrics.mrr == 1.0
