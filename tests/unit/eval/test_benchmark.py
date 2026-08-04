"""Characterization tests for eval/runners/benchmark.py.

Lot 4 (docs/refactoring-plan.md), Part 2. BenchmarkReport's properties and
BenchmarkRunner.run()'s failure handling had no direct tests before this
(55% line coverage per the Lot 3 baseline, concentrated in the untested
branches this file exercises).
"""
from __future__ import annotations

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.eval.runners.benchmark import BenchmarkCase, BenchmarkReport, BenchmarkRunner


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


def test_runner_swallows_engine_failures_into_indistinguishable_empty_metrics() -> None:
    """**Known gap, docs/refactoring-plan.md §2 ('Metric correctness' /
    'Benchmark infrastructure failures fail the run; they do not produce
    empty metrics' invariant in §10.4).** `BenchmarkRunner.run()` catches
    *any* exception from `engine.answer()`, logs a warning, and appends a
    bare `Metrics()` (all fields None) for that case — the same shape a
    genuinely-scored-but-all-null case would have. The report has no way to
    tell "the engine crashed on this case" apart from "this case legitimately
    scored nothing." Characterized, not fixed here (Lot 13 owns this).
    """
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
    assert failed_case_metrics == Metrics()  # indistinguishable from a real null score
    # The average silently absorbs the failure as if it were a valid data point:
    assert report.avg_answer_relevance == 1.0  # only the successful case counts (mean of [1.0])
