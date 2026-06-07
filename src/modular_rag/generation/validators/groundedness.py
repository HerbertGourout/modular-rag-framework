"""Basic groundedness validator: flag answers that contain no citation-based evidence."""
from __future__ import annotations

import re

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.retrieved import RetrievedChunk


class GroundednessValidator:
    """Check whether an answer's text overlaps meaningfully with the retrieved context."""

    def __init__(self, min_overlap_ratio: float = 0.05) -> None:
        self.min_overlap_ratio = min_overlap_ratio

    def validate(self, answer: Answer, context: list[RetrievedChunk]) -> float:
        """Return a groundedness score in [0, 1]."""
        if not context or not answer.text:
            return 0.0
        answer_tokens = set(re.findall(r"\w+", answer.text.lower()))
        context_tokens = set(
            token
            for rc in context
            for token in re.findall(r"\w+", rc.chunk.content.lower())
        )
        if not answer_tokens:
            return 0.0
        overlap = answer_tokens & context_tokens
        return len(overlap) / len(answer_tokens)
