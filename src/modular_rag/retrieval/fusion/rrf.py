from __future__ import annotations

from modular_rag.core.models.retrieved import RetrievedChunk

# Standard RRF constant from Cormack et al. 2009 (SIGIR) — the original RRF paper.
# Not re-validated by the current research corpus (docs/research/DIGEST-retrieval.md #6);
# nothing contradicts it either. Tune on the golden set in V1.1 if needed.
_RRF_K = 60


def reciprocal_rank_fusion(
    lists: list[list[RetrievedChunk]],
    k: int = 10,
    rrf_k: int = _RRF_K,
    weights: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Merge multiple ranked lists using weighted Reciprocal Rank Fusion (Cormack et al. 2009).

    `weights` scales each list's contribution (e.g. vector vs. BM25 trust). Defaults to
    uniform weighting (1.0 per list), which reproduces unweighted RRF.
    """
    if weights is None:
        weights = [1.0] * len(lists)

    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}

    for weight, ranked_list in zip(weights, lists, strict=True):
        for rank, item in enumerate(ranked_list):
            cid = item.chunk.id
            scores[cid] = scores.get(cid, 0.0) + weight / (rrf_k + rank + 1)
            if cid not in best or item.score > best[cid].score:
                best[cid] = item

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]
    return [best[cid] for cid in sorted_ids]
