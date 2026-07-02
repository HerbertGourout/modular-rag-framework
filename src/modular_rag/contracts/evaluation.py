from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


@runtime_checkable
class Evaluator(Protocol):
    """Score an Answer against a Query and optional gold standard."""

    def evaluate(
        self,
        query: Query,
        answer: Answer,
        expected: Answer | None = None,
        context: list[RetrievedChunk] | None = None,
    ) -> Metrics: ...

    def name(self) -> str: ...


@runtime_checkable
class AnswerEngine(Protocol):
    """Minimal QA engine interface consumed by evaluation runners."""

    def answer(self, question: str, **query_kwargs: object) -> Answer: ...
