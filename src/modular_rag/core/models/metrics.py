from __future__ import annotations

from pydantic import BaseModel


class Metrics(BaseModel):
    recall_at_k: float | None = None
    precision_at_k: float | None = None
    ndcg: float | None = None
    mrr: float | None = None
    groundedness: float | None = None
    faithfulness: float | None = None
    answer_relevance: float | None = None
    context_precision: float | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

    def summary(self) -> dict[str, float]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
