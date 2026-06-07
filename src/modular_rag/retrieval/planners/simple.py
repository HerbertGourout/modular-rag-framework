from __future__ import annotations

from modular_rag.contracts.planning import ExecutionPlan, ExecutionStep
from modular_rag.core.enums import RoutingStrategy
from modular_rag.core.models.query import Query


class SimplePlanner:
    """Always plan a single retrieve → generate flow (V1 default)."""

    def name(self) -> str:
        return "simple"

    def plan(self, query: Query) -> ExecutionPlan:
        return ExecutionPlan(
            query_id=query.id,
            strategy=RoutingStrategy.SIMPLE_RAG,
            steps=[
                ExecutionStep(name="retrieve", tool="retriever"),
                ExecutionStep(name="generate", tool="generator", depends_on=["retrieve"]),
            ],
        )
