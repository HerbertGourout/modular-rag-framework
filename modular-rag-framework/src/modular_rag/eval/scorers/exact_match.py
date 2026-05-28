from __future__ import annotations

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class ExactMatchEvaluator:
    """Basic evaluator: exact-match F1 between predicted and expected answer text."""

    def name(self) -> str:
        return "exact-match"

    def evaluate(
        self,
        query: Query,
        answer: Answer,
        expected: "str | Answer | None" = None,
        context: list[RetrievedChunk] | None = None,
    ) -> Metrics:
        if expected is None:
            return Metrics()
        gold_text = expected if isinstance(expected, str) else expected.text
        pred_tokens = set(answer.text.lower().split())
        gold_tokens = set(gold_text.lower().split())
        tp = pred_tokens & gold_tokens
        precision = len(tp) / len(pred_tokens) if pred_tokens else 0.0
        recall = len(tp) / len(gold_tokens) if gold_tokens else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        return Metrics(precision_at_k=precision, recall_at_k=recall, answer_relevance=f1)
