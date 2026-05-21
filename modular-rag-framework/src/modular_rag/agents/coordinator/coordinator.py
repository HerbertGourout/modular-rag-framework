"""Coordinator agent (V2): dispatches tasks to specialised agents."""
from __future__ import annotations

import structlog

from modular_rag.contracts.agents import Agent, AgentResult, AgentTask
from modular_rag.contracts.planning import ExecutionPlan
from modular_rag.core.enums import AgentRole
from modular_rag.core.models.query import Query

log = structlog.get_logger(__name__)


class CoordinatorAgent:
    """Orchestrate a multi-agent pipeline by dispatching ExecutionPlan steps."""

    def __init__(self, agents: dict[AgentRole, Agent]) -> None:
        self._agents = agents

    def role(self) -> AgentRole:
        return AgentRole.COORDINATOR

    def name(self) -> str:
        return "coordinator"

    def execute_plan(self, plan: ExecutionPlan, query: Query) -> list[AgentResult]:
        results: list[AgentResult] = []
        for step in plan.steps:
            agent = self._route_step(step.tool)
            if agent is None:
                log.warning("coordinator.no_agent", tool=step.tool)
                continue
            task = AgentTask(
                name=step.name,
                role=agent.role(),
                query=query,
                instructions=str(step.args),
            )
            result = agent.run(task)
            results.append(result)
            log.debug("coordinator.step_done", step=step.name, role=agent.role())
        return results

    def _route_step(self, tool: str) -> Agent | None:
        for role, agent in self._agents.items():
            if role.value in tool or agent.name() in tool:
                return agent
        return None
