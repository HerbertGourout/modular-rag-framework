---
name: design-retriever-fusion
description: Workflow for designing and implementing retriever fusion (vector + lexical + other)
---

# Design Retriever Fusion Skill

_Originally authored as a workflow for `retrieval-specialist`, invoked as `/design-retriever-fusion`._


Systematic workflow for designing and implementing hybrid retriever fusion strategies.

## State of the Art First (mandatory)

Before choosing fusion weights, `rrf_k`, or reranking strategy, read the research digests and cite the arXiv id backing each parameter choice:

- [docs/research/DIGEST-retrieval.md](../../../docs/research/DIGEST-retrieval.md) — over-fetch→rerank shape validated (retrieve ~20, keep 4-8); rrf_k=60 and 0.7/0.3 weights are unsourced defaults to tune on the golden set; dense-leg quality (hard negatives) outweighs fusion-constant tuning
- [docs/research/DIGEST-evaluation.md](../../../docs/research/DIGEST-evaluation.md) — fusion validation (BM25 closes the lexical gap), reranker regression metric (Δ nDCG@k before/after at small k), late-interaction cross-encoders
- [docs/research/DIGEST-overviews.md](../../../docs/research/DIGEST-overviews.md) — hybrid+RRF SOTA confirmation (RankRAG +7.8% MRR@10, RAG-Fusion +9%), post-retrieval context filtering (FILCO)

If a design choice contradicts the digests, justify it explicitly in the MR.

## When to Use

- Need better retrieval combining multiple signals
- Have multiple retrievers (vector, BM25) to combine
- Want to balance recall and precision
- Need domain-specific ranking

## Retriever Types to Fuse

| Type | Strength | Weakness |
|------|----------|----------|
| Vector (Dense) | Semantic similarity | Misses keyword matches |
| BM25 (Lexical) | Exact keyword matching | Fails on synonyms |
| Hybrid (Fused) | Both signals | More complex |

## Workflow Steps

### 1. Assess Retriever Characteristics (10 min)

**Profile each retriever:**

```python
def profile_retriever(retriever, queries: list[str]):
    """Understand retriever behavior."""
    
    results = {
        "name": retriever.__class__.__name__,
        "avg_top_score": [],
        "avg_diversity": [],
        "avg_latency": []
    }
    
    for query in queries:
        import time
        start = time.time()
        retrieved = retriever.retrieve(query, k=10)
        latency = time.time() - start
        
        # Score distribution
        scores = [r.score for r in retrieved]
        results["avg_top_score"].append(scores[0] if scores else 0)
        
        # Diversity (lower = more similar results)
        embeddings = [embed(r.text) for r in retrieved]
        diversity = compute_diversity(embeddings)
        results["avg_diversity"].append(diversity)
        
        results["avg_latency"].append(latency)
    
    # Compute averages
    return {
        "name": results["name"],
        "avg_top_score": statistics.mean(results["avg_top_score"]),
        "avg_diversity": statistics.mean(results["avg_diversity"]),
        "avg_latency": statistics.mean(results["avg_latency"])
    }

# Profile retrievers
vector_profile = profile_retriever(vector_retriever, test_queries)
bm25_profile = profile_retriever(bm25_retriever, test_queries)

print(f"Vector: score={vector_profile['avg_top_score']:.2f}, latency={vector_profile['avg_latency']*1000:.0f}ms")
print(f"BM25: score={bm25_profile['avg_top_score']:.2f}, latency={bm25_profile['avg_latency']*1000:.0f}ms")
```

### 2. Choose Fusion Algorithm (15 min)

**Algorithm comparison:**

#### Reciprocal Rank Fusion (RRF)
```python
def reciprocal_rank_fusion(results_list: list[list[SearchResult]], k: float = 60):
    """Fuse results using RRF formula: 1/(k + rank)"""
    
    fused_scores = {}
    
    for retriever_results in results_list:
        for rank, result in enumerate(retriever_results, 1):
            doc_id = result.doc_id
            rrf_score = 1.0 / (k + rank)
            
            if doc_id not in fused_scores:
                fused_scores[doc_id] = result
            
            fused_scores[doc_id].score += rrf_score
    
    # Sort by fused score
    fused = sorted(fused_scores.items(), key=lambda x: x[1].score, reverse=True)
    return [result for _, result in fused]
```

**Advantages:**
- No parameter tuning needed
- Works with any number of rankers
- Doesn't require score normalization

#### Weighted Score Combination
```python
def weighted_combination(
    vector_results: list[SearchResult],
    bm25_results: list[SearchResult],
    vector_weight: float = 0.6,
    bm25_weight: float = 0.4
):
    """Combine scores with learned weights."""
    
    # Normalize scores to [0, 1]
    vector_max = max((r.score for r in vector_results), default=1.0)
    bm25_max = max((r.score for r in bm25_results), default=1.0)
    
    # Create score maps
    vector_map = {r.doc_id: r.score / vector_max for r in vector_results}
    bm25_map = {r.doc_id: r.score / bm25_max for r in bm25_results}
    
    # Combine
    all_docs = set(vector_map.keys()) | set(bm25_map.keys())
    fused_scores = {}
    
    for doc_id in all_docs:
        v_score = vector_map.get(doc_id, 0.0)
        b_score = bm25_map.get(doc_id, 0.0)
        fused_scores[doc_id] = vector_weight * v_score + bm25_weight * b_score
    
    # Sort and return top-k
    sorted_docs = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs[:10]
```

**Advantages:**
- Learnable weights
- Can optimize for specific objectives
- More flexible

### 3. Implement Fusion Retriever (20 min)

**Template:**

```python
from modular_rag.contracts.retrieval import RetrieverProtocol, SearchResult
from modular_rag.core.trace import Trace, TraceStep

class HybridRetriever(RetrieverProtocol):
    """Fuse vector and BM25 retrieval."""
    
    def __init__(
        self,
        vector_retriever: RetrieverProtocol,
        bm25_retriever: RetrieverProtocol,
        fusion_method: str = "rrf",
        vector_weight: float = 0.6,
        top_k: int = 10
    ):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.fusion_method = fusion_method
        self.vector_weight = vector_weight
        self.top_k = top_k
    
    async def retrieve(
        self,
        query: str,
        k: int = 10,
        **kwargs
    ) -> list[SearchResult]:
        """Retrieve using hybrid fusion."""
        step = TraceStep(component="HybridRetriever", method="retrieve")
        
        try:
            # 1. Get results from both retrievers (parallel)
            import asyncio
            vector_results, bm25_results = await asyncio.gather(
                self.vector_retriever.retrieve(query, k=k),
                self.bm25_retriever.retrieve(query, k=k)
            )
            
            # 2. Fuse results
            if self.fusion_method == "rrf":
                fused = self._rrf_fusion(vector_results, bm25_results)
            else:
                fused = self._weighted_fusion(vector_results, bm25_results)
            
            # 3. Rerank with cross-encoder (optional)
            if hasattr(self, 'reranker'):
                fused = await self.reranker.rerank(query, fused, k=k)
            
            # 4. Track metrics
            step.metadata = {
                "vector_count": len(vector_results),
                "bm25_count": len(bm25_results),
                "fused_count": len(fused),
                "fusion_method": self.fusion_method,
                "top_score": fused[0].score if fused else 0.0
            }
            
            return fused[:k]
            
        except Exception as e:
            step.status = "error"
            step.error = str(e)
            raise
        finally:
            Trace.add_step(step)
    
    def _rrf_fusion(
        self,
        vector_results: list[SearchResult],
        bm25_results: list[SearchResult],
        k: float = 60
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion."""
        fused_scores = {}
        
        for rank, result in enumerate(vector_results, 1):
            doc_id = result.doc_id
            rrf_score = 1.0 / (k + rank)
            fused_scores[doc_id] = result
            fused_scores[doc_id].score = rrf_score
        
        for rank, result in enumerate(bm25_results, 1):
            doc_id = result.doc_id
            rrf_score = 1.0 / (k + rank)
            
            if doc_id in fused_scores:
                fused_scores[doc_id].score += rrf_score
            else:
                fused_scores[doc_id] = result
                fused_scores[doc_id].score = rrf_score
        
        # Sort by fused score
        fused = sorted(fused_scores.items(), key=lambda x: x[1].score, reverse=True)
        return [result for _, result in fused]
    
    def _weighted_fusion(
        self,
        vector_results: list[SearchResult],
        bm25_results: list[SearchResult]
    ) -> list[SearchResult]:
        """Weighted score combination."""
        # Normalize scores
        vector_max = max((r.score for r in vector_results), default=1.0)
        bm25_max = max((r.score for r in bm25_results), default=1.0)
        
        vector_map = {r.doc_id: r.score / vector_max for r in vector_results}
        bm25_map = {r.doc_id: r.score / bm25_max for r in bm25_results}
        
        # Combine with weights
        fused_scores = {}
        for doc_id in set(vector_map.keys()) | set(bm25_map.keys()):
            v_score = vector_map.get(doc_id, 0.0)
            b_score = bm25_map.get(doc_id, 0.0)
            combined = self.vector_weight * v_score + (1 - self.vector_weight) * b_score
            
            # Find original result
            for r in vector_results + bm25_results:
                if r.doc_id == doc_id:
                    result = r
                    result.score = combined
                    fused_scores[doc_id] = result
                    break
        
        # Sort and return
        fused = sorted(fused_scores.items(), key=lambda x: x[1].score, reverse=True)
        return [result for _, result in fused]
```

### 4. Test Fusion Strategy (20 min)

**Benchmark against baselines:**

```python
def benchmark_fusion(
    vector_retriever,
    bm25_retriever,
    hybrid_retriever,
    test_queries: list[str],
    golden_set: dict
):
    """Compare retriever performance."""
    
    results = {}
    
    for retriever_name, retriever in [
        ("vector", vector_retriever),
        ("bm25", bm25_retriever),
        ("hybrid", hybrid_retriever)
    ]:
        scores = []
        for query in test_queries:
            retrieved = retriever.retrieve(query, k=10)
            
            # Calculate NDCG
            ndcg = compute_ndcg(retrieved, golden_set[query])
            scores.append(ndcg)
        
        results[retriever_name] = {
            "avg_ndcg": statistics.mean(scores),
            "min_ndcg": min(scores),
            "max_ndcg": max(scores)
        }
    
    return results

# Run benchmark
benchmark_results = benchmark_fusion(
    vector_retriever,
    bm25_retriever,
    hybrid_retriever,
    test_queries,
    golden_set
)

# Compare
for name, metrics in benchmark_results.items():
    print(f"{name}: NDCG@10 = {metrics['avg_ndcg']:.3f}")
```

### 5. Optimize Fusion Weights (15 min)

**Learn weights from golden set:**

```python
from scipy.optimize import minimize

def learn_fusion_weights(
    vector_results_list: list[list[SearchResult]],
    bm25_results_list: list[list[SearchResult]],
    golden_set: dict[str, list[str]]
):
    """Find optimal fusion weights."""
    
    def objective(weights):
        """Objective: minimize (1 - average NDCG)."""
        vector_weight = weights[0]
        bm25_weight = 1 - vector_weight
        
        total_ndcg = 0
        
        for query_id, (vector_results, bm25_results) in enumerate(
            zip(vector_results_list, bm25_results_list)
        ):
            # Fuse with current weights
            fused = weighted_combination(
                vector_results,
                bm25_results,
                vector_weight=vector_weight
            )
            
            # Compute NDCG
            ndcg = compute_ndcg(fused, golden_set[query_id])
            total_ndcg += ndcg
        
        return -(total_ndcg / len(vector_results_list))  # Minimize negative NDCG
    
    # Optimize
    result = minimize(objective, x0=[0.5], bounds=[(0, 1)])
    
    optimal_weight = result.x[0]
    return {"vector_weight": optimal_weight, "bm25_weight": 1 - optimal_weight}

# Learn weights
optimal_weights = learn_fusion_weights(
    vector_results_by_query,
    bm25_results_by_query,
    golden_set
)

print(f"Optimal weights: vector={optimal_weights['vector_weight']:.2f}, bm25={optimal_weights['bm25_weight']:.2f}")
```

### 6. Add Reranking (Optional) (10 min)

**Use cross-encoder for precision:**

```python
class HybridRetrieverWithReranking(HybridRetriever):
    def __init__(self, *args, reranker=None, reranker_k: int = 5, **kwargs):
        super().__init__(*args, **kwargs)
        self.reranker = reranker
        self.reranker_k = reranker_k
    
    async def retrieve(self, query: str, k: int = 10) -> list[SearchResult]:
        # 1. Get fused results
        fused = await super().retrieve(query, k=k*2)  # Get more for reranking
        
        # 2. Rerank top candidates
        if self.reranker:
            fused[:self.reranker_k] = await self.reranker.rerank(
                query,
                fused[:self.reranker_k]
            )
        
        return fused[:k]
```

## Fusion Algorithm Comparison

| Algorithm | Complexity | Tuning | Performance |
|-----------|-----------|--------|-------------|
| RRF | O(n log n) | None | Good, stable |
| Weighted | O(n log n) | 1 param | Better, needs data |
| Learned | O(n) train | All | Best, overfitting risk |

## Success Criteria

✅ Hybrid NDCG@10 > individual retrievers
✅ Fusion latency < 100ms
✅ Fusion method documented
✅ Weights optimized or justified
✅ Reranking (if used) improves precision
✅ Tested with golden set

## Time Estimate

**Total:** 2-3 hours including design, implementation, and optimization
