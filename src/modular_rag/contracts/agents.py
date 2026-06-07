from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from modular_rag.core.enums import AgentRole
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


@dataclass
class AgentTask:
    name: str
    role: AgentRole
    query: Query
    context: list[RetrievedChunk] = field(default_factory=list)
    instructions: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    task_name: str
    role: AgentRole
    output: str
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Agent(Protocol):
    """A specialized agent that performs one role in an agentic RAG pipeline (V2+)."""

    def run(self, task: AgentTask) -> AgentResult: ...

    async def arun(self, task: AgentTask) -> AgentResult: ...

    def role(self) -> AgentRole: ...

    def name(self) -> str: ...
