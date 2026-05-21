"""Retriever agent (V2): wraps the Retriever contract as an Agent for agentic pipelines."""
from __future__ import annotations

from modular_rag.contracts.agents import AgentResult, AgentTask
from modular_rag.contracts.retrieval import Retriever
from modular_rag.core.enums import AgentRole


class RetrieverAgent:
    """Execute retrieval as part of a multi-agent workflow."""

    def __init__(self, retriever: Retriever, k: int = 10) -> None:
        self._retriever = retriever
        self._k = k

    def role(self) -> AgentRole:
        return AgentRole.RETRIEVER

    def name(self) -> str:
        return "retriever_agent"

    def run(self, task: AgentTask) -> AgentResult:
        chunks = self._retriever.retrieve(task.query, k=self._k)
        return AgentResult(
            task_name=task.name,
            role=AgentRole.RETRIEVER,
            output=f"Retrieved {len(chunks)} chunks.",
            retrieved=chunks,
        )

    async def arun(self, task: AgentTask) -> AgentResult:
        return self.run(task)
