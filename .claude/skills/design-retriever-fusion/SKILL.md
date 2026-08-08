---
name: design-retriever-fusion
description: Workflow for tuning or extending retriever fusion (vector + lexical + other)
---

# Design Retriever Fusion Skill

_Originally authored as a workflow for `retrieval-specialist`, invoked as `/design-retriever-fusion`._

> **Corrected 2026-08-06** (documentation-utility pass): this file previously presented fusion
> as something to build from scratch — a `HybridRetriever(RetrieverProtocol)` with async-only
> `retrieve(query: str, ...) -> list[SearchResult]`, and a hand-rolled `_rrf_fusion()` — none of
> which matches reality. **Both already exist**: `HybridRetriever`
> (`src/modular_rag/retrieval/retrievers/hybrid.py`) fuses `VectorRetriever` + `BM25Retriever`
> today, and RRF itself lives in `reciprocal_rank_fusion()`
> (`src/modular_rag/retrieval/fusion/rrf.py`, Cormack et al. 2009, weighted). This skill is for
> **tuning the existing fusion weights or adding a third signal to it**, not writing fusion from
> zero — rewritten below to point at the real code instead of reimplementing it.

Systematic workflow for tuning and extending hybrid retriever fusion.

## State of the Art First (mandatory)

Before choosing fusion weights, `rrf_k`, or reranking strategy, read the research digests and cite the arXiv id backing each parameter choice:

- [docs/research/DIGEST-retrieval.md](../../../docs/research/DIGEST-retrieval.md) — over-fetch→rerank shape validated (retrieve ~20, keep 4-8); `rrf_k=60` (the module-level default in `fusion/rrf.py`) and the 0.7/0.3 vector/BM25 weights (the constructor defaults in `hybrid.py`) are unsourced engineering priors to tune on the golden set; dense-leg quality (hard negatives) outweighs fusion-constant tuning
- [docs/research/DIGEST-evaluation.md](../../../docs/research/DIGEST-evaluation.md) — fusion validation (BM25 closes the lexical gap), reranker regression metric (Δ nDCG@k before/after at small k), late-interaction cross-encoders
- [docs/research/DIGEST-overviews.md](../../../docs/research/DIGEST-overviews.md) — hybrid+RRF SOTA confirmation (RankRAG +7.8% MRR@10, RAG-Fusion +9%), post-retrieval context filtering (FILCO)

If a design choice contradicts the digests, justify it explicitly in the MR.

## When to Use

- Tuning `HybridRetriever`'s `vector_weight`/`bm25_weight` on a new domain's golden set
- Adding a third ranked signal (e.g. a reranker pass, or a new retriever type) into the existing
  RRF fusion
- Diagnosing why fusion underperforms one of its individual legs

## Existing Building Blocks

| Component | File | Notes |
|---|---|---|
| `HybridRetriever` | `src/modular_rag/retrieval/retrievers/hybrid.py` | Sync `retrieve(query: Query, k: int) -> list[RetrievedChunk]`; owns a `VectorRetriever` + `BM25Retriever` internally, over-fetches `k*2` from each, falls back to whichever side is available if one errors |
| `reciprocal_rank_fusion` | `src/modular_rag/retrieval/fusion/rrf.py` | `(lists: list[list[RetrievedChunk]], k, rrf_k=60, weights=None) -> list[RetrievedChunk]` — weighted RRF, Cormack et al. 2009 |
| `RetrievedChunk` | `src/modular_rag/core/models/retrieved.py` | The real result type — there is no `SearchResult` class in this codebase |

## Retriever Types to Fuse

| Type | Strength | Weakness |
|------|----------|----------|
| Vector (Dense) | Semantic similarity | Misses keyword matches |
| BM25 (Lexical) | Exact keyword matching | Fails on synonyms |
| Hybrid (Fused) | Both signals | More complex |

## Workflow Steps

### 1. Assess Retriever Characteristics (10 min)

**Profile each retriever** — note the real, synchronous `Retriever` signature
(`retrieve(query: Query, k: int) -> list[RetrievedChunk]`); this is illustrative profiling code,
not a Protocol requirement:

```python
import statistics
import time

def profile_retriever(retriever, queries: list[Query]):
    """Understand retriever behavior."""
    latencies, top_scores = [], []
    for query in queries:
        t0 = time.perf_counter()
        retrieved = retriever.retrieve(query, k=10)
        latencies.append(time.perf_counter() - t0)
        top_scores.append(retrieved[0].score if retrieved else 0.0)

    return {
        "name": retriever.name(),
        "avg_top_score": statistics.mean(top_scores),
        "avg_latency_ms": statistics.mean(latencies) * 1000,
    }
```

### 2. Tune the Existing Fusion (15 min)

`HybridRetriever` already does RRF fusion via `reciprocal_rank_fusion()` — you're tuning its
constructor args, not choosing between algorithms from scratch:

```python
# vector_weight / bm25_weight passed straight to HybridRetriever's constructor,
# which forwards them as `weights=[vector_weight, bm25_weight]` to reciprocal_rank_fusion()
retriever = HybridRetriever(vector_weight=0.7, bm25_weight=0.3, k=20, reranker_k=5)
```

`reciprocal_rank_fusion()` itself takes `rrf_k` (the RRF smoothing constant, default 60 — this
is the "no normalization needed" advantage of RRF over raw weighted-score combination) and
`weights` (per-list multipliers). If you need a from-scratch weighted **score** (not rank)
combination for comparison, note that requires score normalization first (RRF's main advantage
is avoiding exactly that step) — do this only as an experiment, not a replacement, unless the
golden-set numbers clearly favor it.

### 3. Add a Third Signal (Optional, 20 min)

`reciprocal_rank_fusion()` already accepts an arbitrary number of ranked lists — adding a third
signal (e.g. a graph retriever, if one is ever wired per
[ADR-0005](../../../docs/adr/0005-document-ai-control-plane-boundary.md)'s delegation
boundary) means extending `HybridRetriever.retrieve()` to gather a third list and pass
`weights=[w1, w2, w3]`, not writing a new fusion function:

```python
# Inside a modified retrieve(): gather a third ranked list, then
fused = reciprocal_rank_fusion(
    [vector_hits, bm25_hits, third_hits],
    k=k,
    weights=[self.vector_weight, self.bm25_weight, self.third_weight],
)
```

### 4. Benchmark Against Baselines (20 min)

```python
import statistics

def benchmark_fusion(retrievers: dict, test_queries: list[Query], golden_set: dict):
    """Compare retriever performance (NDCG@10)."""
    results = {}
    for name, retriever in retrievers.items():
        scores = [
            compute_ndcg(retriever.retrieve(q, k=10), golden_set[q.id])
            for q in test_queries
        ]
        results[name] = {
            "avg_ndcg": statistics.mean(scores),
            "min_ndcg": min(scores),
            "max_ndcg": max(scores),
        }
    return results
```

`compute_ndcg` isn't a shipped function — see `src/modular_rag/eval/scorers/` for the real
scorer implementations (`ExactMatchEvaluator` today) before writing a new NDCG scorer, and add
it there if it doesn't exist yet.

### 5. Optimize Fusion Weights (15 min)

```python
from scipy.optimize import minimize

def learn_fusion_weights(vector_lists, bm25_lists, golden_set):
    """Find the vector_weight that maximizes average NDCG (bm25_weight = 1 - vector_weight)."""
    def objective(weights):
        vector_weight = weights[0]
        fused_lists = [
            reciprocal_rank_fusion([v, b], k=10, weights=[vector_weight, 1 - vector_weight])
            for v, b in zip(vector_lists, bm25_lists)
        ]
        avg_ndcg = statistics.mean(
            compute_ndcg(fused, golden_set[i]) for i, fused in enumerate(fused_lists)
        )
        return -avg_ndcg

    result = minimize(objective, x0=[0.7], bounds=[(0, 1)])
    return {"vector_weight": result.x[0], "bm25_weight": 1 - result.x[0]}
```

### 6. Reranking (Already Wired)

`HybridRetriever` takes `reranker_k` in its constructor and `CrossEncoderReranker` is already
registered (`app/default_factories.py`, `reg.register("reranker", "cross-encoder",
...)`) — reranking is a manifest-config concern (select the reranker in your YAML), not
something to hand-build inside a retriever subclass.

## Fusion Algorithm Comparison

| Algorithm | Complexity | Tuning | Performance |
|-----------|-----------|--------|-------------|
| RRF (shipped) | O(n log n) | `rrf_k`, per-list weights | Good, stable, no score normalization needed |
| Weighted score combination | O(n log n) | Requires score normalization | Better only with reliable score scales, needs data |
| Learned weights | O(n) train | All | Best, overfitting risk |

## Success Criteria

✅ Hybrid NDCG@10 > individual retrievers
✅ Fusion latency < 100ms
✅ Weight choice documented and either research-cited or golden-set-justified
✅ Reranking (if used) improves precision
✅ Tested with golden set

## Time Estimate

**Total:** 1-2 hours for tuning existing fusion; 2-3 hours if adding a genuinely new third signal
