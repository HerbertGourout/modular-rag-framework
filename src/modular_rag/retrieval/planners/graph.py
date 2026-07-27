"""Graph-aware multi-hop planner (V3)."""
from __future__ import annotations

from modular_rag.contracts.planning import ExecutionPlan, ExecutionStep
from modular_rag.core.enums import RoutingStrategy
from modular_rag.core.models.query import Query


class GraphPlanner:
    """Plan a graph_retrieve → vector_retrieve → generate flow for multi-hop questions (V3)."""

    def name(self) -> str:
        return "graph"

    def plan(self, query: Query) -> ExecutionPlan:
        return ExecutionPlan(
            query_id=query.id,
            strategy=RoutingStrategy.GRAPH_RAG,
            steps=[
                ExecutionStep(name="entity_extract", tool="enricher"),
                ExecutionStep(
                    name="graph_retrieve", tool="graph_store", depends_on=["entity_extract"]
                ),
                ExecutionStep(
                    name="vector_retrieve", tool="retriever", depends_on=["graph_retrieve"]
                ),
                ExecutionStep(name="generate", tool="generator", depends_on=["vector_retrieve"]),
            ],
        )
