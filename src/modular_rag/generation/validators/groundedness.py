"""Cheap lexical-support gate for generated answers (token-overlap heuristic).

This is a *lexical-support gate*, NOT a faithfulness metric. It measures the
fraction of answer tokens that also appear anywhere in the retrieved context —
a cheap, training-free signal for "did the answer reuse the vocabulary of the
sources". Per the Survey of Retrieval-Augmented Text Generation in LLMs
(arXiv:2404.10981 §7), lexical overlap is a legitimate cheap *filter* (FILCO's
Lexical Overlap strategy) but is explicitly positioned *below* semantic /
statement-level checks and is never the faithfulness measure the literature
endorses.

Faithfulness proper — ``supported statements / total statements``, RAGAS-style
and LLM/semantic-judged (arXiv:2404.10981 §7, Table 1) — is a separate, more
expensive check scheduled for the V1.1 Evaluation-as-Contract milestone. Do not
mistake the score returned here for that metric.

The class name is retained for API stability; its semantics are a lexical gate,
not groundedness/faithfulness scoring.
"""
from __future__ import annotations

import re

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.retrieved import RetrievedChunk


class GroundednessValidator:
    """Cheap lexical-support gate: fraction of answer tokens present in context.

    This is NOT a faithfulness metric. It is a lexical-overlap heuristic in the
    sense of FILCO's Lexical Overlap context filter (arXiv:2404.10981 §5), used
    as a cheap gate before more expensive semantic checks. Faithfulness proper
    (supported-statements / total-statements, RAGAS-style; arXiv:2404.10981 §7)
    is deferred to the V1.1 Evaluation-as-Contract milestone.
    """

    def __init__(self, min_overlap_ratio: float = 0.05) -> None:
        # NOTE: 0.05 is an UNCALIBRATED heuristic with no basis in the
        # literature (arXiv:2404.10981 sets no such threshold). Treat it as a
        # value to calibrate on the golden set in V1.1, not a validated default.
        self.min_overlap_ratio = min_overlap_ratio

    def validate(self, answer: Answer, context: list[RetrievedChunk]) -> float:
        """Return a lexical-support score in [0, 1].

        The score is ``|answer_tokens ∩ context_tokens| / |answer_tokens|`` — a
        cheap lexical gate, NOT a faithfulness/groundedness measure
        (arXiv:2404.10981 §7).
        """
        if not context or not answer.text:
            return 0.0
        answer_tokens = set(re.findall(r"\w+", answer.text.lower()))
        context_tokens = {
            token
            for rc in context
            for token in re.findall(r"\w+", rc.chunk.content.lower())
        }
        if not answer_tokens:
            return 0.0
        overlap = answer_tokens & context_tokens
        return len(overlap) / len(answer_tokens)
