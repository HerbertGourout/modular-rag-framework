from __future__ import annotations

from modular_rag.core.models.retrieved import RetrievedChunk

_RRF_K = 60  # standard RRF constant


def reciprocal_rank_fusion(
    lists: list[list[RetrievedChunk]],
    k: int = 10,
    rrf_k: int = _RRF_K,
) -> list[RetrievedChunk]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion (Cormack et al. 2009)."""
    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}

    for ranked_list in lists:
        for rank, item in enumerate(ranked_list):
            cid = item.chunk.id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            if cid not in best or item.score > best[cid].score:
                best[cid] = item

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]
    return [best[cid] for cid in sorted_ids]
