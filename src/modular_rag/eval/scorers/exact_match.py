from __future__ import annotations

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class ExactMatchEvaluator:
    """Answer-level evaluator: genuine exact-match plus a token-set F1 signal.

    Fixed in Lot 13 (docs/refactoring-plan.md — "correct metric vocabulary and
    formulas"): this class previously computed only token-set precision/recall/F1
    and wrote them into `Metrics.precision_at_k`/`recall_at_k` — fields
    `eval/scorers/retrieval_metrics.py` defines as *retrieval* metrics (over
    retrieved chunks vs. a relevant-id set), not answer metrics. A class named
    "exact match" that never checked for exact equality, writing into fields
    reserved for a different metric family entirely, is now two separate,
    correctly-named things:
    - `exact_match`: genuine normalized (lowercased, whitespace-collapsed)
      string equality — 1.0 or 0.0, nothing in between.
    - `answer_precision`/`answer_recall`/`answer_relevance`: the token-set
      overlap signal this class always computed, kept because it's a useful
      softer metric, now in the answer-scoped fields it always should have
      used.
    """

    def name(self) -> str:
        return "exact-match"

    def evaluate(
        self,
        query: Query,
        answer: Answer,
        expected: str | Answer | None = None,
        context: list[RetrievedChunk] | None = None,
    ) -> Metrics:
        if expected is None:
            return Metrics()
        gold_text = expected if isinstance(expected, str) else expected.text

        exact_match = 1.0 if self._normalize(answer.text) == self._normalize(gold_text) else 0.0

        pred_tokens = set(answer.text.lower().split())
        gold_tokens = set(gold_text.lower().split())
        tp = pred_tokens & gold_tokens
        precision = len(tp) / len(pred_tokens) if pred_tokens else 0.0
        recall = len(tp) / len(gold_tokens) if gold_tokens else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return Metrics(
            exact_match=exact_match,
            answer_precision=precision,
            answer_recall=recall,
            answer_relevance=f1,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())
