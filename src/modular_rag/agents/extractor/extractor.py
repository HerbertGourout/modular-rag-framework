"""Extractor agent (V2/V3): extract entities and key facts from retrieved chunks."""
from __future__ import annotations

import re

from modular_rag.contracts.agents import AgentResult, AgentTask
from modular_rag.core.enums import AgentRole

_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b")


class ExtractorAgent:
    """Extract named entities and key phrases from retrieved context."""

    def role(self) -> AgentRole:
        return AgentRole.EXTRACTOR

    def name(self) -> str:
        return "extractor"

    def run(self, task: AgentTask) -> AgentResult:
        entities: list[str] = []
        for rc in task.context:
            found = _ENTITY_RE.findall(rc.chunk.content)
            entities.extend(found)
        unique_entities = list(dict.fromkeys(entities))[:30]
        return AgentResult(
            task_name=task.name,
            role=AgentRole.EXTRACTOR,
            output=", ".join(unique_entities),
            retrieved=task.context,
            metadata={"entities": unique_entities},
        )

    async def arun(self, task: AgentTask) -> AgentResult:
        return self.run(task)
