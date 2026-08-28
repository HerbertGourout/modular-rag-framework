"""Unit tests for eval/scorers/answer_correctness.py (Batch 13, external
plan — "Offline benchmark")."""
from __future__ import annotations

from modular_rag.eval.scorers.answer_correctness import (
    answer_correctness_score,
    compute_answer_correctness,
)


def test_identical_text_scores_one() -> None:
    assert answer_correctness_score("30 days", "30 days") == 1.0


def test_case_and_whitespace_differences_are_normalized_away() -> None:
    assert answer_correctness_score("  30   DAYS ", "30 days") == 1.0


def test_completely_different_text_scores_low() -> None:
    score = answer_correctness_score("The sky is blue today.", "30 days")

    assert score < 0.3


def test_is_sensitive_to_word_order_unlike_token_set_overlap() -> None:
    """The exact property token-set F1 (answer_relevance) cannot see:
    reordering the same words changes this score, since SequenceMatcher
    operates on contiguous matching subsequences, not a bag of words."""
    same_words_reordered = answer_correctness_score("dog bites man", "man bites dog")
    identical_order = answer_correctness_score("dog bites man", "dog bites man")

    assert same_words_reordered < identical_order
    assert identical_order == 1.0


def test_compute_answer_correctness_wraps_the_score_into_metrics() -> None:
    metrics = compute_answer_correctness("30 days", "30 days")

    assert metrics.answer_correctness == 1.0
    assert metrics.faithfulness is None  # unrelated field, untouched
