from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from modular_rag.core.enums import RoutingStrategy
from modular_rag.core.models.query import Query


@dataclass
class ExecutionStep:
    name: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    query_id: str
    strategy: RoutingStrategy
    steps: list[ExecutionStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Planner(Protocol):
    """Analyse a Query and produce an ExecutionPlan (V2+)."""

    def plan(self, query: Query) -> ExecutionPlan: ...

    def name(self) -> str: ...
