"""Unit tests for eval/quality_gate.py — QualityGate. Lot 13,
docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest

from modular_rag.eval.quality_gate import GateMode, QualityGate, QualityGateError


def test_report_only_mode_does_not_raise_on_violation():
    gate = QualityGate({"avg_answer_relevance": 0.9}, mode=GateMode.REPORT_ONLY)

    result = gate.check({"avg_answer_relevance": 0.5})  # must not raise

    assert result.passed is False
    assert len(result.violations) == 1
    assert result.violations[0].metric == "avg_answer_relevance"
    assert result.violations[0].baseline == 0.9
    assert result.violations[0].actual == 0.5


def test_report_only_mode_passes_when_no_regression():
    gate = QualityGate({"avg_answer_relevance": 0.9}, mode=GateMode.REPORT_ONLY)

    result = gate.check({"avg_answer_relevance": 0.95})

    assert result.passed is True
    assert result.violations == []


def test_blocking_mode_raises_on_violation():
    gate = QualityGate({"avg_answer_relevance": 0.9}, mode=GateMode.BLOCKING)

    with pytest.raises(QualityGateError) as exc_info:
        gate.check({"avg_answer_relevance": 0.5})

    assert exc_info.value.result.passed is False
    assert len(exc_info.value.result.violations) == 1


def test_blocking_mode_does_not_raise_when_no_regression():
    gate = QualityGate({"avg_answer_relevance": 0.9}, mode=GateMode.BLOCKING)

    result = gate.check({"avg_answer_relevance": 0.9})  # exactly at baseline — must not raise

    assert result.passed is True


def test_tolerance_allows_a_small_regression():
    gate = QualityGate({"avg_answer_relevance": 0.9}, mode=GateMode.REPORT_ONLY, tolerance=0.05)

    result = gate.check({"avg_answer_relevance": 0.87})  # within tolerance

    assert result.passed is True


def test_missing_metric_in_actual_is_treated_as_zero_fail_closed():
    gate = QualityGate({"avg_answer_relevance": 0.5}, mode=GateMode.REPORT_ONLY)

    result = gate.check({})  # metric absent entirely

    assert result.passed is False
    assert result.violations[0].actual == 0.0


def test_multiple_metrics_all_checked():
    gate = QualityGate(
        {"avg_answer_relevance": 0.9, "avg_recall": 0.8}, mode=GateMode.REPORT_ONLY
    )

    result = gate.check({"avg_answer_relevance": 0.5, "avg_recall": 0.5})

    assert len(result.violations) == 2
