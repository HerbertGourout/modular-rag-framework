from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from modular_rag.contracts.evaluation import AnswerEngine, Evaluator
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query

log = structlog.get_logger(__name__)

GOLDEN_SET_SCHEMA_VERSION = "1.0"  # Lot 13, docs/refactoring-plan.md — "version quality
# and golden-dataset schemas." Bump when a case's *shape* changes (new required field),
# not when the underlying data content is updated.


@dataclass
class BenchmarkCase:
    question: str
    expected_answer: str
    relevant_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class GoldenSet:
    """A versioned, named collection of `BenchmarkCase`s (Lot 13). Distinct
    from a bare `list[BenchmarkCase]`: carries a `schema_version` and a
    `name`/`domain` label, so a golden set is an identifiable, comparable
    artifact — "did this domain's golden set regress" — rather than an
    anonymous list a caller has to track separately."""

    name: str
    cases: list[BenchmarkCase]
    schema_version: str = GOLDEN_SET_SCHEMA_VERSION
    domain: str = "default"

    def __len__(self) -> int:
        return len(self.cases)


@dataclass
class BenchmarkReport:
    total: int
    metrics_per_case: list[Metrics]

    @property
    def failed_count(self) -> int:
        """Cases where the engine call itself raised — distinct from cases
        that ran and scored zero (Lot 13, docs/refactoring-plan.md —
        "distinguish infrastructure failure from zero quality")."""
        return sum(1 for m in self.metrics_per_case if m.failed)

    @property
    def failure_rate(self) -> float:
        return self.failed_count / self.total if self.total else 0.0

    @property
    def avg_answer_relevance(self) -> float:
        values = [
            m.answer_relevance
            for m in self.metrics_per_case
            if m.answer_relevance is not None and not m.failed
        ]
        return sum(values) / len(values) if values else 0.0

    @property
    def avg_recall(self) -> float:
        values = [
            m.recall_at_k
            for m in self.metrics_per_case
            if m.recall_at_k is not None and not m.failed
        ]
        return sum(values) / len(values) if values else 0.0

    def quality_summary(self) -> dict[str, float]:
        """"Higher is better" aggregate metrics, suitable input for
        `eval.quality_gate.QualityGate.check()`. Deliberately excludes
        `failure_rate` (lower is better — inverted direction, would need a
        different gate comparison than the rest)."""
        return {
            "avg_answer_relevance": self.avg_answer_relevance,
            "avg_recall": self.avg_recall,
        }


class BenchmarkRunner:
    """Run a set of QA cases through an answer engine and aggregate metrics."""

    def __init__(self, engine: AnswerEngine, evaluator: Evaluator) -> None:
        self.engine = engine
        self.evaluator = evaluator

    def run(self, cases: list[BenchmarkCase]) -> BenchmarkReport:
        metrics_list: list[Metrics] = []
        for case in cases:
            try:
                answer = self.engine.answer(case.question)
                expected = Answer(query_id="", text=case.expected_answer)
                query = Query(text=case.question)
                m = self.evaluator.evaluate(query, answer, expected=expected)
            except Exception as exc:
                # Lot 13 (docs/refactoring-plan.md): a bare Metrics() here was
                # indistinguishable from a genuinely null-scoring case — the
                # report had no way to tell "the engine crashed" apart from
                # "this legitimately scored nothing." Metrics.for_failure()
                # records that this case never actually ran.
                log.warning("benchmark.case_failed", question=case.question[:60], error=str(exc))
                m = Metrics.for_failure(str(exc))
            metrics_list.append(m)
        report = BenchmarkReport(total=len(cases), metrics_per_case=metrics_list)
        log.info(
            "benchmark.done",
            total=report.total,
            avg_f1=report.avg_answer_relevance,
            failed=report.failed_count,
        )
        return report
