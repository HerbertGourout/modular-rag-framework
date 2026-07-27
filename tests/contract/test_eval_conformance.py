"""Contract conformance tests for Evaluator implementations."""
from __future__ import annotations

import pytest

from modular_rag.contracts.evaluation import Evaluator
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.eval.scorers.exact_match import ExactMatchEvaluator

EVALUATORS = [ExactMatchEvaluator()]


@pytest.mark.parametrize("evaluator", EVALUATORS, ids=lambda e: e.name())
def test_implements_evaluator_protocol(evaluator):
    assert isinstance(evaluator, Evaluator)


@pytest.mark.parametrize("evaluator", EVALUATORS, ids=lambda e: e.name())
def test_name_returns_string(evaluator):
    assert isinstance(evaluator.name(), str)


@pytest.mark.parametrize("evaluator", EVALUATORS, ids=lambda e: e.name())
def test_evaluate_returns_metrics(evaluator):
    q = Query(text="What is RAG?")
    a = Answer(query_id=q.id, text="Retrieval-Augmented Generation")
    result = evaluator.evaluate(q, a, expected="Retrieval-Augmented Generation")
    assert isinstance(result, Metrics)
