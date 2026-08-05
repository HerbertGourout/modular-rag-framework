"""Tests for eval/runners/benchmark.py.

Originally characterization tests (Lot 4, docs/refactoring-plan.md Part 2).
Lot 13 fixed the failure-masking bug the last test used to characterize —
that test now proves the fix instead.
"""
from __future__ import annotations

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.eval.runners.benchmark import (
    GOLDEN_SET_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkRunner,
    GoldenSet,
)


class _FakeEngine:
    def __init__(self, *, raise_on: str | None = None) -> None:
        self._raise_on = raise_on

    def answer(self, question: str, **kwargs: object) -> Answer:
        if self._raise_on is not None and question == self._raise_on:
            raise RuntimeError(f"engine exploded on: {question}")
        return Answer(query_id="q", text=question.upper())


class _FakeEvaluator:
    def name(self) -> str:
        return "fake"

    def evaluate(self, query, answer, expected=None, context=None) -> Metrics:  # type: ignore[no-untyped-def]
        return Metrics(answer_relevance=1.0, recall_at_k=0.8)


def test_report_avg_answer_relevance_ignores_none_values() -> None:
    report = BenchmarkReport(
        total=3,
        metrics_per_case=[
            Metrics(answer_relevance=1.0),
            Metrics(answer_relevance=0.5),
            Metrics(answer_relevance=None),
        ],
    )

    assert report.avg_answer_relevance == 0.75


def test_report_avg_answer_relevance_is_zero_when_every_case_is_none() -> None:
    report = BenchmarkReport(total=2, metrics_per_case=[Metrics(), Metrics()])

    assert report.avg_answer_relevance == 0.0
    assert report.avg_recall == 0.0


def test_runner_evaluates_every_case_and_reports_averages() -> None:
    runner = BenchmarkRunner(engine=_FakeEngine(), evaluator=_FakeEvaluator())
    cases = [
        BenchmarkCase(question="What is RAG?", expected_answer="Retrieval-Augmented Generation"),
        BenchmarkCase(question="What is BM25?", expected_answer="A ranking function"),
    ]

    report = runner.run(cases)

    assert report.total == 2
    assert report.avg_answer_relevance == 1.0
    assert report.avg_recall == 0.8
    assert report.failed_count == 0
    assert report.failure_rate == 0.0


def test_runner_records_engine_failures_as_failed_not_as_null_scores() -> None:
    """Fixed in Lot 13 (docs/refactoring-plan.md — "distinguish infrastructure
    failure from zero quality"): a case whose engine call raises is now
    recorded with Metrics.failed=True, not a bare Metrics() indistinguishable
    from a genuinely null-scoring case."""
    runner = BenchmarkRunner(
        engine=_FakeEngine(raise_on="this one blows up"), evaluator=_FakeEvaluator()
    )
    cases = [
        BenchmarkCase(question="a normal question", expected_answer="a normal answer"),
        BenchmarkCase(question="this one blows up", expected_answer="never scored"),
    ]

    report = runner.run(cases)  # does not raise

    assert report.total == 2
    failed_case_metrics = report.metrics_per_case[1]
    assert failed_case_metrics.failed is True
    assert "engine exploded" in failed_case_metrics.failure_reason
    assert failed_case_metrics != Metrics()  # no longer indistinguishable
    assert report.failed_count == 1
    assert report.failure_rate == 0.5
    # The average still only counts the successful case — now explicit via
    # BenchmarkReport's `not m.failed` filter, not incidental to `is not None`.
    assert report.avg_answer_relevance == 1.0


def test_quality_summary_excludes_failure_rate() -> None:
    report = BenchmarkReport(
        total=2,
        metrics_per_case=[Metrics(answer_relevance=1.0, recall_at_k=0.8), Metrics.for_failure("x")],
    )

    summary = report.quality_summary()

    assert summary == {"avg_answer_relevance": 1.0, "avg_recall": 0.8}
    assert "failure_rate" not in summary


def test_golden_set_has_a_schema_version_and_len():
    cases = [BenchmarkCase(question="q1", expected_answer="a1")]
    golden = GoldenSet(name="finance-basics", cases=cases, domain="finance")

    assert golden.schema_version == GOLDEN_SET_SCHEMA_VERSION
    assert len(golden) == 1
    assert golden.domain == "finance"
