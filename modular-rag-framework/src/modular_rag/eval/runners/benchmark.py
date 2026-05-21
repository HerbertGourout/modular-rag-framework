from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from modular_rag.contracts.evaluation import Evaluator
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.orchestration.engine import RAGEngine

log = structlog.get_logger(__name__)


@dataclass
class BenchmarkCase:
    question: str
    expected_answer: str
    relevant_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    total: int
    metrics_per_case: list[Metrics]

    @property
    def avg_answer_relevance(self) -> float:
        values = [m.answer_relevance for m in self.metrics_per_case if m.answer_relevance is not None]
        return sum(values) / len(values) if values else 0.0

    @property
    def avg_recall(self) -> float:
        values = [m.recall_at_k for m in self.metrics_per_case if m.recall_at_k is not None]
        return sum(values) / len(values) if values else 0.0


class BenchmarkRunner:
    """Run a set of QA cases through a RAGEngine and aggregate metrics."""

    def __init__(self, engine: RAGEngine, evaluator: Evaluator) -> None:
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
                log.warning("benchmark.case_failed", question=case.question[:60], error=str(exc))
                m = Metrics()
            metrics_list.append(m)
        report = BenchmarkReport(total=len(cases), metrics_per_case=metrics_list)
        log.info("benchmark.done", total=report.total, avg_f1=report.avg_answer_relevance)
        return report
