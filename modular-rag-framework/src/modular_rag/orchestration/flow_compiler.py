from __future__ import annotations

from modular_rag.contracts.planning import ExecutionPlan, ExecutionStep
from modular_rag.core.enums import RoutingStrategy
from modular_rag.core.models.query import Query


class FlowCompiler:
    """Compile a RoutingStrategy into a concrete ExecutionPlan."""

    def compile(self, query: Query, strategy: RoutingStrategy) -> ExecutionPlan:
        match strategy:
            case RoutingStrategy.LLM_ONLY:
                steps = [ExecutionStep(name="generate", tool="generator", args={"use_context": False})]
            case RoutingStrategy.SIMPLE_RAG:
                steps = [
                    ExecutionStep(name="retrieve", tool="retriever"),
                    ExecutionStep(name="rerank", tool="reranker", depends_on=["retrieve"]),
                    ExecutionStep(name="generate", tool="generator", depends_on=["rerank"]),
                ]
            case RoutingStrategy.AGENTIC_RAG:
                steps = [
                    ExecutionStep(name="plan", tool="planner"),
                    ExecutionStep(name="retrieve", tool="retriever_agent", depends_on=["plan"]),
                    ExecutionStep(name="synthesize", tool="synthesizer_agent", depends_on=["retrieve"]),
                    ExecutionStep(name="validate", tool="validator_agent", depends_on=["synthesize"]),
                    ExecutionStep(name="output", tool="generator", depends_on=["validate"]),
                ]
            case RoutingStrategy.GRAPH_RAG:
                steps = [
                    ExecutionStep(name="graph_retrieve", tool="graph_retriever"),
                    ExecutionStep(name="retrieve", tool="retriever", depends_on=["graph_retrieve"]),
                    ExecutionStep(name="generate", tool="generator", depends_on=["retrieve"]),
                ]
            case _:
                steps = [
                    ExecutionStep(name="retrieve", tool="retriever"),
                    ExecutionStep(name="generate", tool="generator", depends_on=["retrieve"]),
                ]

        return ExecutionPlan(query_id=query.id, strategy=strategy, steps=steps)
