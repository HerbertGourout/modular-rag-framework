from __future__ import annotations

from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.retrieved import RetrievedChunk


def recall_at_k(retrieved: list[RetrievedChunk], relevant_ids: set[str], k: int) -> float:
    top_k = {rc.chunk.id for rc in retrieved[:k]}
    if not relevant_ids:
        return 0.0
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved: list[RetrievedChunk], relevant_ids: set[str], k: int) -> float:
    top_k = list(retrieved[:k])
    if not top_k:
        return 0.0
    return sum(1 for rc in top_k if rc.chunk.id in relevant_ids) / len(top_k)


def mrr(retrieved: list[RetrievedChunk], relevant_ids: set[str]) -> float:
    for rank, rc in enumerate(retrieved, 1):
        if rc.chunk.id in relevant_ids:
            return 1.0 / rank
    return 0.0


def compute_retrieval_metrics(
    retrieved: list[RetrievedChunk],
    relevant_ids: set[str],
    k: int = 5,
) -> Metrics:
    return Metrics(
        recall_at_k=recall_at_k(retrieved, relevant_ids, k),
        precision_at_k=precision_at_k(retrieved, relevant_ids, k),
        mrr=mrr(retrieved, relevant_ids),
    )
