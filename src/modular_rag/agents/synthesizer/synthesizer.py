"""Synthesizer agent (V2): merge evidence from multiple retrievals into a coherent answer."""
from __future__ import annotations

from modular_rag.contracts.agents import AgentResult, AgentTask
from modular_rag.core.enums import AgentRole


class SynthesizerAgent:
    """Summarise and integrate retrieved evidence into a structured draft answer."""

    def role(self) -> AgentRole:
        return AgentRole.SYNTHESIZER

    def name(self) -> str:
        return "synthesizer"

    def run(self, task: AgentTask) -> AgentResult:
        combined = "\n\n".join(rc.chunk.content for rc in task.context[:5])
        draft = f"Based on the available evidence:\n\n{combined[:2000]}"
        return AgentResult(
            task_name=task.name,
            role=AgentRole.SYNTHESIZER,
            output=draft,
            retrieved=task.context,
        )

    async def arun(self, task: AgentTask) -> AgentResult:
        return self.run(task)
