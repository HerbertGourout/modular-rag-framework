"""Unit tests for ExactMatchEvaluator."""
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
    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0


def test_no_overlap():
    q, a = _qa("What is RAG?", "apple banana cherry")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="dog cat fish")
    assert metrics.precision_at_k == 0.0
    assert metrics.recall_at_k == 0.0


def test_partial_overlap():
    q, a = _qa("Describe RAG", "RAG uses retrieval to augment generation")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="RAG uses retrieval for better answers")
    assert 0.0 < metrics.precision_at_k < 1.0
    assert 0.0 < metrics.recall_at_k < 1.0


def test_case_insensitive():
    q, a = _qa("What?", "The Answer Is Forty Two")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected="the answer is forty two")
    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0


def test_no_expected_returns_none_scores():
    q, a = _qa("What is RAG?", "some answer")
    metrics = ExactMatchEvaluator().evaluate(q, a, expected=None)
    assert metrics.precision_at_k is None
    assert metrics.recall_at_k is None


def test_class_named_exact_match_actually_computes_token_set_f1_not_exact_equality():
    """Known naming/behavior mismatch (docs/refactoring-plan.md §2, 'Evaluation
    and trace correctness'): despite the class name, this is token-set
    precision/recall/F1 — not a strict string-equality exact-match check.
    A prediction that reorders or repeats the gold tokens scores a perfect
    1.0/1.0 here, which a real exact-match evaluator would never do.
    """
    q, a = _qa("What is RAG?", "Generation Augmented Retrieval Retrieval Retrieval")
    metrics = ExactMatchEvaluator().evaluate(
        q, a, expected="Retrieval Augmented Generation"
    )

    # Reordered AND repeated tokens still score a perfect match under set
    # intersection — proof this isn't exact string/sequence equality.
    assert a.text != "Retrieval Augmented Generation"
    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0
