"""Unit tests for eval/scorers/faithfulness.py (Batch 13, external plan —
"Offline benchmark")."""
from __future__ import annotations

from modular_rag.eval.scorers.faithfulness import compute_faithfulness, faithfulness_score


def test_fully_quoted_answer_scores_one() -> None:
    context = ["Our refund policy allows returns within 30 days of purchase."]
    answer = "Our refund policy allows returns within 30 days of purchase."

    assert faithfulness_score(answer, context) == 1.0


def test_answer_with_no_overlap_scores_zero() -> None:
    context = ["Our refund policy allows returns within 30 days of purchase."]
    answer = "The weather today is sunny and warm."

    assert faithfulness_score(answer, context) == 0.0


def test_partial_overlap_scores_between_zero_and_one() -> None:
    context = ["Our refund policy allows returns within 30 days of purchase."]
    answer = "Returns are allowed within 30 days, subject to additional conditions not listed here."

    score = faithfulness_score(answer, context)

    assert 0.0 < score < 1.0


def test_empty_answer_scores_zero_not_a_division_error() -> None:
    assert faithfulness_score("", ["some context"]) == 0.0


def test_empty_context_scores_zero_even_with_a_real_answer() -> None:
    """A non-empty answer grounded in nothing has nothing to be faithful to
    -- scored 0.0, not vacuously 1.0."""
    assert faithfulness_score("some answer text", []) == 0.0


def test_is_case_insensitive() -> None:
    assert faithfulness_score("REFUND POLICY", ["refund policy applies here"]) == 1.0


def test_compute_faithfulness_wraps_the_score_into_metrics() -> None:
    metrics = compute_faithfulness("30 days", ["Returns within 30 days are accepted."])

    assert metrics.faithfulness == 1.0
    assert metrics.answer_correctness is None  # unrelated field, untouched
