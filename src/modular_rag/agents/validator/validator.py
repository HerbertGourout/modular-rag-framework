"""Validator / critic agent (V2): check answer coherence and groundedness."""
from __future__ import annotations

import re

from modular_rag.contracts.agents import AgentResult, AgentTask
from modular_rag.core.enums import AgentRole
from modular_rag.core.models.retrieved import RetrievedChunk

MIN_GROUNDEDNESS = 0.05


class ValidatorAgent:
    """Check that a draft answer is grounded in the retrieved context."""

    def role(self) -> AgentRole:
        return AgentRole.VALIDATOR

    def name(self) -> str:
        return "validator"

    def run(self, task: AgentTask) -> AgentResult:
        score = _groundedness_score(task.instructions or "", task.context)
        output = task.instructions or ""
        if score < MIN_GROUNDEDNESS:
            output += (
                "\n\n[Validator warning: low groundedness — answer may contain hallucinations.]"
            )
        return AgentResult(
            task_name=task.name,
            role=AgentRole.VALIDATOR,
            output=output,
            retrieved=task.context,
            confidence=score,
        )

    async def arun(self, task: AgentTask) -> AgentResult:
        return self.run(task)


def _groundedness_score(answer_text: str, context: list[RetrievedChunk]) -> float:
    """Return token-overlap groundedness in [0, 1] without crossing domains."""
    if not context or not answer_text:
        return 0.0
    answer_tokens = set(re.findall(r"\w+", answer_text.lower()))
    context_tokens = set(
        token
        for retrieved in context
        for token in re.findall(r"\w+", retrieved.chunk.content.lower())
    )
    if not answer_tokens:
        return 0.0
    return len(answer_tokens & context_tokens) / len(answer_tokens)
