from __future__ import annotations

import math

from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.retrieved import RetrievedChunk

# Batch 13 (external plan — "Offline benchmark"; not this repo's own
# docs/refactoring-plan.md Lot numbering, which already used "Lot 13" for an
# unrelated, already-completed metric-vocabulary fix — see that Lot's own
# history if grepping "Lot 13" in this repo).
#
# These functions accept either a plain, ordered `list[str]` of chunk ids or
# the historical `list[RetrievedChunk]` shape — `_normalize_ids()` below
# converts either into the `list[str]` form every function actually computes
# against. A benchmark scores retrieval quality from
# `Answer.citations[*].chunk_id` (`core/models/answer.py::Citation`), not
# from a live `list[RetrievedChunk]` — `AnswerEngine` (contracts/evaluation.py)
# only exposes `answer()`, never raw retrieved chunks, and extending that
# Protocol just to plumb them through for offline scoring would be exactly
# the kind of runtime-path change ADR-0008 says not to make ("avoid
# introducing an expected reference into the runtime path"). `list[str]` is
# the shape a citation-based caller produces naturally.
#
# Codex review (pass 1, HIGH-002): an earlier version of this module widened
# every signature from `list[RetrievedChunk]` to `list[str]` outright,
# reasoning that zero real callers existed anywhere in `src/` (confirmed by
# grep) so nothing broke. That reasoning doesn't hold once a Protocol's
# public surface is considered independently of this repo's own callers —
# `compute_retrieval_metrics` is re-exported through `eval.__all__`, so an
# external consumer built against the old `list[RetrievedChunk]` signature
# would get a `TypeError: unhashable type: 'Chunk'` from `recall_at_k()`'s
# `set(retrieved_ids[:k])`, not a type-checker warning. `_normalize_ids()`
# accepts both shapes so this is genuinely additive rather than a disguised
# breaking change.

Retrieved = list[str] | list[RetrievedChunk]


def _normalize_ids(retrieved: Retrieved) -> list[str]:
    """Accept either shape: a plain ordered `list[str]` of chunk ids (the
    benchmark's own shape), or the historical `list[RetrievedChunk]` (a live
    retrieval result). Assumes a homogeneous list — the only two shapes any
    real caller (in this repo or historically) has ever produced."""
    if retrieved and isinstance(retrieved[0], RetrievedChunk):
        return retrieved_chunk_ids(retrieved)
    return list(retrieved)  # type: ignore[arg-type]


def recall_at_k(retrieved_ids: Retrieved, relevant_ids: set[str], k: int) -> float:
    ids = _normalize_ids(retrieved_ids)
    top_k = set(ids[:k])
    if not relevant_ids:
        return 0.0
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved_ids: Retrieved, relevant_ids: set[str], k: int) -> float:
    ids = _normalize_ids(retrieved_ids)
    top_k = ids[:k]
    if not top_k:
        return 0.0
    return sum(1 for cid in top_k if cid in relevant_ids) / len(top_k)


def mrr(retrieved_ids: Retrieved, relevant_ids: set[str]) -> float:
    ids = _normalize_ids(retrieved_ids)
    for rank, cid in enumerate(ids, 1):
        if cid in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: Retrieved, relevant_ids: set[str], k: int) -> float:
    """Binary-relevance NDCG@k, exactly per the formula in
    docs/research/DIGEST-evaluation.md #1 ([2504.14891]):
    `DCG@k = sum((2^rel_i - 1) / log2(i+1))` for 1-indexed rank `i`, with
    `rel_i` in `{0, 1}` here (no graded relevance labels in this codebase's
    golden-set schema — see `eval/runners/benchmark.py::BenchmarkCase`).
    `IDCG@k` is the same sum for the ideal ordering (all relevant ids first).
    Returns `0.0` when there is nothing to rank against, matching the other
    functions in this module rather than raising or returning `nan`.

    Codex review (pass 1, MEDIUM-003): each id counts toward gain at most
    once — the first time it appears in `retrieved_ids`. Without this, a
    retriever that returns the same relevant id more than once (a real
    retrieval-layer bug, not a benchmark artifact) could earn gain for every
    duplicate while `IDCG@k` still only counts each relevant id once, so
    `DCG@k` could exceed `IDCG@k` and this function could return a value
    above `1.0` — impossible for a property that must stay in `[0, 1]`.
    """
    ids = _normalize_ids(retrieved_ids)
    if not relevant_ids or not ids or k <= 0:
        return 0.0

    def _dcg(relevances: list[int]) -> float:
        return float(
            sum((2**rel - 1) / math.log2(i + 1) for i, rel in enumerate(relevances, start=1))
        )

    seen: set[str] = set()
    actual_gains: list[int] = []
    for cid in ids[:k]:
        gain = 1 if (cid in relevant_ids and cid not in seen) else 0
        actual_gains.append(gain)
        seen.add(cid)
    dcg = _dcg(actual_gains)

    # Ideal ordering: every relevant id ranked first, capped at k positions
    # (a case may declare fewer relevant chunks than k, or more than were
    # ever retrieved for it).
    ideal_relevant_count = min(len(relevant_ids), k)
    ideal_gains = [1] * ideal_relevant_count + [0] * (k - ideal_relevant_count)
    idcg = _dcg(ideal_gains)

    return dcg / idcg if idcg > 0 else 0.0


def compute_retrieval_metrics(
    retrieved_ids: Retrieved,
    relevant_ids: set[str],
    k: int = 5,
) -> Metrics:
    return Metrics(
        recall_at_k=recall_at_k(retrieved_ids, relevant_ids, k),
        precision_at_k=precision_at_k(retrieved_ids, relevant_ids, k),
        mrr=mrr(retrieved_ids, relevant_ids),
        ndcg=ndcg_at_k(retrieved_ids, relevant_ids, k),
    )


def retrieved_chunk_ids(retrieved: list[RetrievedChunk]) -> list[str]:
    """Convenience adapter for a hypothetical future caller that already has
    real `RetrievedChunk` objects (e.g. a retrieval-only regression check) —
    kept here rather than duplicated at each call site."""
    return [rc.chunk.id for rc in retrieved]
