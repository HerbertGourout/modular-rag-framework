"""Unit tests for ExactMatchEvaluator. Lot 13 (docs/refactoring-plan.md)
fixed the metric-vocabulary bug this file's last test used to characterize:
answer-level scores now land in `answer_precision`/`answer_recall`/
`answer_relevance`, not the retrieval-scoped `precision_at_k`/`recall_at_k`,
and a genuine `exact_match` field now exists.
"""
from __future__ import annotations

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.eval.scorers.exact_match import ExactMatchEvaluator


def _qa(question: str, answer_text: str) -> tuple[Query, Answer]:
    q = Query(text=question)
    a = Answer(query_id=q.id, text=answer_text)
    return q, a


def test_name():
    evaluator = ExactMatchEvaluator()
    assert evaluator.name() == "exact-match"


def test_perfect_match():
    q, a = _qa("What is RAG?", "Retrieval-Augmented Generation")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="Retrieval-Augmented Generation")
    assert metrics.answer_precision == 1.0
    assert metrics.answer_recall == 1.0
    assert metrics.exact_match == 1.0


def test_no_overlap():
    q, a = _qa("What is RAG?", "apple banana cherry")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="dog cat fish")
    assert metrics.answer_precision == 0.0
    assert metrics.answer_recall == 0.0
    assert metrics.exact_match == 0.0


def test_partial_overlap():
    q, a = _qa("Describe RAG", "RAG uses retrieval to augment generation")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="RAG uses retrieval for better answers")
    assert 0.0 < metrics.answer_precision < 1.0
    assert 0.0 < metrics.answer_recall < 1.0
    assert metrics.exact_match == 0.0


def test_case_insensitive():
    q, a = _qa("What?", "The Answer Is Forty Two")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="the answer is forty two")
    assert metrics.answer_precision == 1.0
    assert metrics.answer_recall == 1.0
    assert metrics.exact_match == 1.0  # normalization is case-insensitive too


def test_no_expected_returns_none_scores():
    q, a = _qa("What is RAG?", "some answer")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected=None)
    assert metrics.answer_precision is None
    assert metrics.answer_recall is None
    assert metrics.exact_match is None


def test_retrieval_scoped_fields_are_never_touched():
    """The core Lot 13 regression: an answer-level evaluator must not write
    into precision_at_k/recall_at_k, which eval/scorers/retrieval_metrics.py
    defines as retrieval-scoped."""
    q, a = _qa("What is RAG?", "Retrieval-Augmented Generation")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="Retrieval-Augmented Generation")

    assert metrics.precision_at_k is None
    assert metrics.recall_at_k is None


def test_reordered_and_repeated_tokens_score_high_f1_but_not_exact_match():
    """Token-set F1 (answer_relevance) is a softer signal than exact_match by
    design — a reordered/repeated-token prediction can still score near-perfect
    F1, but exact_match correctly rejects it. Distinguishing these two is the
    whole point of Lot 13's fix."""
    q, a = _qa("What is RAG?", "Generation Augmented Retrieval Retrieval Retrieval")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="Retrieval Augmented Generation")

    assert a.text != "Retrieval Augmented Generation"
    assert metrics.answer_precision == 1.0
    assert metrics.answer_recall == 1.0
    assert metrics.exact_match == 0.0  # not literally equal — correctly rejected


def test_exact_match_ignores_surrounding_whitespace_differences():
    q, a = _qa("What?", "  forty   two  ")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="forty two")
    assert metrics.exact_match == 1.0
