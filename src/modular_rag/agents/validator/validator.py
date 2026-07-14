"""Validator / critic agent (V2): check answer coherence and groundedness."""
from __future__ import annotations

from modular_rag.contracts.agents import AgentResult, AgentTask
from modular_rag.core.enums import AgentRole
from modular_rag.generation.validators.groundedness import GroundednessValidator

_validator = GroundednessValidator(min_overlap_ratio=0.05)


class ValidatorAgent:
    """Check that a draft answer is grounded in the retrieved context."""

    def role(self) -> AgentRole:
        return AgentRole.VALIDATOR

    def name(self) -> str:
        return "validator"

    def run(self, task: AgentTask) -> AgentResult:
        from modular_rag.core.models.answer import Answer

        draft_answer = Answer(query_id=task.query.id, text=task.instructions or "")
        score = _validator.validate(draft_answer, task.context)
        output = task.instructions or ""
        if score < 0.05:
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
