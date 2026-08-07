# Claude Code Parallelization & Orchestration Guide

**Version:** 1.0  
**Target:** V1.x (basic parallelization); native multi-agent orchestration is delegated per ADR-0005  
**Updated:** 2026-08-06

> **Corrected 2026-08-06** (documentation-utility pass): §11 below used to claim
> `.claude/settings.json` has a working `"parallelization": {"enabled": true, ...}` key. It
> doesn't — that file's own `notes.removedFromV1` field says explicitly this key is
> **"narrative-only, never read by Claude Code"** and points back at this document as its home
> as illustrative content, not configuration. Fixed in §11. Separately, per
> [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md), the "V2+ multi-agent
> orchestration" sections (§4, §10, §13 Example 3, §14) describe a *delegated* capability
> (handed to the selected external engine via the `DocumentEngine` port), not a native build
> this framework will implement itself — retained below as historical design intent, not a
> roadmap commitment.

---

## 1. Overview

This guide explains how to use Claude Code's parallelization capabilities for faster RAG framework development and execution.

### What is Parallelization?

**Parallelization** = Running multiple tasks simultaneously instead of sequentially.

**Serial (slow):**
```
Task A (2h) → Task B (2h) → Task C (2h) = 6 hours total
```

**Parallel (fast):**
```
Task A ┐
Task B ├ 2 hours total
Task C ┘
```

### Parallelization in Claude Code

Claude Code supports **three levels** of parallelization:

| Level | What | V1 Support | V2+ Scope |
|-------|------|-----------|----------|
| **Tool-level** | Multiple file reads/writes in single call | ✅ Yes | Native |
| **Component-level** | Retriever fusion (vec + BM25 in parallel) | ✅ Async | Native |
| **Agentic-level** | Multi-agent coordination | ❌ No | Full framework |

---

## 2. Tool-Level Parallelization (V1)

### Parallel File Operations

**Serial (slow):**
```python
# Read files one at a time
doc1 = read_file("docs/doc1.md")
doc2 = read_file("docs/doc2.md")
doc3 = read_file("docs/doc3.md")
# Total: 3 operations × 100ms = 300ms
```

**Parallel (faster):**
```
# All reads "in parallel" via single Claude call
# Claude Code internally optimizes file reads
# Total: 50-100ms (network round-trip)

# Usage: Just call read_file multiple times in sequence
# Claude batches them intelligently
```

### When to Use

- Reading multiple independent files (doc corpus)
- Writing multiple test files
- Searching multiple patterns
- No ordering dependencies

### Example: Parallel Document Ingestion

```python
# Task: Ingest 100 documents into vector store

# ❌ SERIAL (slow): 100 reads × 50ms = 5 seconds
docs = []
for file in glob("docs/*.md"):
    doc = read_file(file)
    docs.append(doc)

# ✅ PARALLEL (fast): ~500ms via Claude batching
# Just call read_file() - Claude optimizes
docs = []
for file in glob("docs/*.md"):
    docs.append(read_file(file))  # Claude batches internally
```

---

## 3. Component-Level Parallelization (V1+)

### Hybrid Retriever Fusion

**Sequential (slow):**
```python
# Retrieve with vector search: 80ms
vec_results = vector_retriever.retrieve(query, k=10)

# Then retrieve with BM25: 30ms
bm25_results = bm25_retriever.retrieve(query, k=10)

# Then fuse: 5ms
fused = rrf_fusion(vec_results, bm25_results)

# Total: 80 + 30 + 5 = 115ms
```

**Parallel (faster):**
```python
# Retrieve with both in parallel: max(80, 30) = 80ms
import asyncio

vec_results, bm25_results = await asyncio.gather(
    vector_retriever.retrieve(query, k=10),
    bm25_retriever.retrieve(query, k=10)
)

# Then fuse: 5ms
fused = rrf_fusion(vec_results, bm25_results)

# Total: 80 + 5 = 85ms (26% faster)
```

### Pattern: Fan-Out / Fan-In

```python
async def hybrid_retrieve(query: str):
    """Retrieve using multiple methods in parallel."""
    
    # Fan-out: Start multiple retrievers
    results = await asyncio.gather(
        vector_retriever.retrieve(query),     # Parallel task 1
        bm25_retriever.retrieve(query),       # Parallel task 2
        # graph_retriever.retrieve(query),    # Could add more (V3+)
    )
    vec, bm25 = results
    
    # Fan-in: Combine results
    fused = fusion_algorithm(vec, bm25)
    return fused
```

### Implementation

**File:** `src/modular_rag/retrieval/hybrid_retriever.py`

```python
from modular_rag.contracts.retrieval import RetrieverProtocol, SearchResult
from modular_rag.core.trace import Trace, TraceStep
import asyncio

class HybridRetriever(RetrieverProtocol):
    """Hybrid retriever using parallel vector + BM25 retrieval."""
    
    def __init__(self, vector_retriever: RetrieverProtocol, bm25_retriever: RetrieverProtocol):
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
    
    async def retrieve(self, query: str, k: int = 10) -> list[SearchResult]:
        """Retrieve using parallel fan-out/fan-in pattern."""
        step = TraceStep(component="HybridRetriever", method="retrieve")
        
        try:
            # PARALLEL EXECUTION (fan-out)
            vector_results, bm25_results = await asyncio.gather(
                self.vector_retriever.retrieve(query, k),
                self.bm25_retriever.retrieve(query, k),
                return_exceptions=True  # Don't fail if one retriever errors
            )
            
            # Handle errors from parallel tasks
            if isinstance(vector_results, Exception):
                vector_results = []
            if isinstance(bm25_results, Exception):
                bm25_results = []
            
            # FUSE RESULTS (fan-in)
            fused = self._rrf_fusion(vector_results, bm25_results)
            
            step.metadata = {
                "vector_count": len(vector_results),
                "bm25_count": len(bm25_results),
                "fused_count": len(fused)
            }
            
            return fused[:k]
            
        except Exception as e:
            step.status = "error"
            raise
        finally:
            Trace.add_step(step)
    
    def _rrf_fusion(self, vec_results, bm25_results):
        """Fuse using Reciprocal Rank Fusion."""
        # Implementation details omitted for brevity
        pass
```

### When to Use Component-Level Parallelization

- Multiple retrievers (vector, BM25, graph)
- Multiple generators (GPT-4, Claude, local LLM)
- Multiple security guards (PII detector, injection filter)
- Multiple evaluation metrics
- Independent analysis tasks

---

## 4. Agentic-Level Parallelization (V2+)

### Multi-Agent Orchestration

**V2+ scope** - Not implemented in V1, but planned structure:

```yaml
# V2 manifest with agent orchestration
agents:
  - name: planner
    role: decompose_tasks
    
  - name: retriever_agent
    role: find_relevant_docs
    depends_on: [planner]
    parallelizable_with: [fact_checker]  # Can run in parallel
    
  - name: fact_checker
    role: verify_facts
    depends_on: [planner]
    parallelizable_with: [retriever_agent]
    
  - name: synthesizer
    role: combine_results
    depends_on: [retriever_agent, fact_checker]

execution:
  mode: dag  # Directed Acyclic Graph scheduling
  parallelism: max_workers=4
```

---

## 5. Skill: Parallel Feature Analysis

The **`/parallel-feature-analysis`** skill provides workflow for analyzing multiple features in parallel:

```python
# Run all feature analyses in parallel
results = await asyncio.gather(
    analyze_retrieval_feature(),
    analyze_generation_feature(),
    analyze_security_feature()
)
```

**Benefits:**
- 3 hours of serial work → 1 hour parallel (3x speedup)
- All features benchmarked in single run
- Results aggregated automatically
- Regressions detected easily

**See:** [`.claude/skills/parallel-feature-analysis/SKILL.md`](../../.claude/skills/parallel-feature-analysis/SKILL.md)

---

## 6. Design Patterns

### Pattern 1: Map-Reduce (Fan-Out / Fan-In)

**Structure:**
```
Map Phase:
  Input → [Task A, Task B, Task C] (parallel)

Reduce Phase:
  [Result A, Result B, Result C] → Aggregate → Output
```

**Example - Retriever Fusion:**
```python
# Map: Distribute to retrievers
vec, bm25, graph = await asyncio.gather(
    vec_retriever.retrieve(query),
    bm25_retriever.retrieve(query),
    graph_retriever.retrieve(query)
)

# Reduce: Aggregate results
fused = aggregate_results(vec, bm25, graph)
```

### Pattern 2: Pipeline (Sequential with Parallelizable Stages)

**Structure:**
```
Stage 1: Ingestion
  Input → [Chunk A, Chunk B, Chunk C] (parallel)
           ↓
Stage 2: Embedding
  [Embeddings A, B, C] (parallel on chunks)
           ↓
Stage 3: Indexing
  [Indexed A, B, C] (sequential, accumulating index)
```

### Pattern 3: Tree (Multi-Level Reduction)

**Structure:**
```
        Final Result
        /    |    \
      Node1 Node2 Node3
      / \    / \    / \
    A   B  C   D  E   F
```

**Example - Multi-Retriever Hierarchy:**
```python
# Level 1: Parallel retrieval
vec1, vec2, bm25 = await asyncio.gather(
    vec_retriever_en.retrieve(query),
    vec_retriever_multilang.retrieve(query),
    bm25_retriever.retrieve(query)
)

# Level 2: Fuse vector retrievers
vec_fused = fuse_vectors(vec1, vec2)

# Level 3: Final fusion
final = fuse_all(vec_fused, bm25)
```

---

## 7. Dependency Resolution

### Independent Tasks (Fully Parallel)

**Can run simultaneously - no ordering dependencies:**

```python
# ✅ Can parallelize
await asyncio.gather(
    read_file("doc1.txt"),
    read_file("doc2.txt"),
    read_file("doc3.txt")
)

# ✅ Can parallelize
await asyncio.gather(
    vector_retriever.retrieve(query),
    bm25_retriever.retrieve(query)
)
```

### Dependent Tasks (Sequential)

**Cannot parallelize - Task B depends on Task A result:**

```python
# ❌ Cannot parallelize - sequential required
retrieval_results = await retriever.retrieve(query)
ranked_results = await reranker.rerank(retrieval_results)  # Depends on retrieval
generated_answer = await generator.generate(ranked_results)  # Depends on ranking
```

### Partial Dependency (Hybrid)

**Some tasks parallel, then dependent step:**

```python
# ✅ Can optimize - vec + bm25 parallel, then fuse
vec, bm25 = await asyncio.gather(
    vector_retriever.retrieve(query),
    bm25_retriever.retrieve(query)
)
fused = fuse_results(vec, bm25)

# Then sequential steps
ranked = await reranker.rerank(fused)
answer = await generator.generate(ranked)
```

---

## 8. Failure Handling

### Fail-Fast Strategy

**If ANY task fails, everything fails:**

```python
try:
    results = await asyncio.gather(
        task_a(),
        task_b(),
        task_c()
    )
except Exception as e:
    # All tasks cancelled
    # Error propagates
```

**Use when:** Critical path - one failure = abort

### Fail-Tolerant Strategy

**If ONE task fails, continue with others:**

```python
results = await asyncio.gather(
    task_a(),
    task_b(),
    task_c(),
    return_exceptions=True  # Don't raise on failure
)

# Filter out exceptions
successful_results = [r for r in results if not isinstance(r, Exception)]
```

**Use when:** Optional retrievers - vec fails, continue with BM25

### Timeout Strategy

**Cancel tasks that take too long:**

```python
try:
    result = await asyncio.wait_for(
        slow_task(),
        timeout=5.0  # Cancel after 5 seconds
    )
except asyncio.TimeoutError:
    result = fallback_result  # Use cached/approximation
```

**Use when:** Slow services - don't block pipeline

---

## 9. Performance Optimization

### Measure Parallelization Impact

```python
import time

# Measure serial time
start = time.time()
vec = await vector_retriever.retrieve(query)
bm25 = await bm25_retriever.retrieve(query)
serial_time = time.time() - start

# Measure parallel time
start = time.time()
vec, bm25 = await asyncio.gather(
    vector_retriever.retrieve(query),
    bm25_retriever.retrieve(query)
)
parallel_time = time.time() - start

# Calculate speedup
speedup = serial_time / parallel_time
print(f"Speedup: {speedup:.2f}x")
```

### Speedup Formula

```
Speedup = T_serial / T_parallel

Expected:
- 2 parallel tasks: speedup ≈ 1.8-1.9x (not 2x due to overhead)
- 3 parallel tasks: speedup ≈ 2.5-2.7x (not 3x)
- 4 parallel tasks: speedup ≈ 3.0-3.3x (not 4x)
```

### Optimization Tactics

| Tactic | Impact | Effort |
|--------|--------|--------|
| Balance task duration | High | Low |
| Minimize synchronization | High | Medium |
| Batch small operations | Medium | Low |
| Async I/O | High | Medium |
| Caching results | High | Medium |

---

## 10. V1 vs V2+ Capabilities

### V1 (Current - Basic)

✅ Parallel file operations (tool-level)  
✅ Async component execution (retriever fusion)  
✅ Simple fan-out/fan-in patterns  
✅ Basic error handling  

❌ No multi-agent coordination  
❌ No complex dependency graphs  
❌ No distributed execution  
❌ No resource management  

### V2+ (Planned - Full)

✅ Multi-agent orchestration  
✅ DAG scheduling (complex dependencies)  
✅ Load balancing  
✅ Resource quotas (CPU, memory, I/O)  
✅ Inter-agent communication  
✅ Consensus mechanisms  
✅ Dynamic routing  

---

## 11. Quick Reference

### Enable Parallelization

There is no setting to toggle: tool-level and component-level parallelization (§2-§3) are just
`asyncio.gather()`/multi-call patterns in your own code and prompts — Claude Code has no
`parallelization` config key. (An earlier version of this section, and of
`.claude/settings.json`, claimed otherwise; see the correction note at the top of this file.)

### Use Pattern: Retriever Fusion

```python
# HybridRetriever implementation
vec, bm25 = await asyncio.gather(
    vector_retriever.retrieve(query, k),
    bm25_retriever.retrieve(query, k)
)
fused = rrf_fusion(vec, bm25)
return fused[:k]
```

### Use Pattern: Parallel Analysis

```python
# Via /parallel-feature-analysis skill
results = await asyncio.gather(
    analyze_retrieval_feature(config),
    analyze_generation_feature(config),
    analyze_security_feature(config)
)
```

### Use Pattern: Timeout Protection

```python
try:
    result = await asyncio.wait_for(task(), timeout=5)
except asyncio.TimeoutError:
    result = fallback_value
```

---

## 12. Troubleshooting

### Issue: No Speedup

**Symptom:** Parallel code not faster than sequential

**Causes:**
- Tasks aren't truly independent (hidden synchronization)
- Coordination overhead > parallelization benefit
- GIL contention (use asyncio, not threading)
- One task much slower than others (load imbalance)

**Fix:**
- Profile to measure individual task times
- Use `asyncio` not `threading` for I/O-bound work
- Balance task durations
- Reduce coordination overhead

### Issue: Deadlock or Circular Wait

**Symptom:** Tasks wait for each other indefinitely

**Causes:**
- Undeclared dependency between tasks
- Shared resource contention
- Missing dependency in DAG

**Fix:**
- Explicitly declare all dependencies
- Use locks/semaphores for shared resources
- Visualize dependency graph

### Issue: Partial Failures

**Symptom:** One task fails, others orphaned

**Causes:**
- Using `asyncio.gather()` without `return_exceptions=True`
- Exception not caught properly

**Fix:**
```python
# Good: Capture exceptions
results = await asyncio.gather(..., return_exceptions=True)

# Check for failures
for result in results:
    if isinstance(result, Exception):
        handle_error(result)
```

---

## 13. Real-World Examples

### Example 1: Hybrid Retrieval (Component-Level)

See [`.claude/skills/design-retriever-fusion/SKILL.md`](../../.claude/skills/design-retriever-fusion/SKILL.md)

### Example 2: Parallel Feature Analysis (Task-Level)

See [`.claude/skills/parallel-feature-analysis/SKILL.md`](../../.claude/skills/parallel-feature-analysis/SKILL.md)

### Example 3: Multi-Agent Orchestration (V2+)

```
# Planned for V2 - not available in V1
agents:
  retriever_agent → find docs (parallel with fact_checker)
  fact_checker → verify facts (parallel with retriever_agent)
  synthesizer → combine (depends on both)
```

---

## 14. Next Steps

### V1 (Current Focus)

✅ Component-level parallelization (retrievers, generators)  
✅ Tool-level parallelization (file operations)  
⏳ Integration with evaluation framework  

### V2 (Next Sprint)

- Multi-agent coordination framework
- DAG-based task scheduling
- Load balancing and resource quotas
- Full agentic parallelization

### V3+ (Future)

- Distributed execution (across machines)
- Federation and clustering
- Real-time monitoring and adjustment

---

## References

- [`.claude/settings.json`](../../.claude/settings.json) - Parallelization configuration
- [`/parallel-feature-analysis` skill](../../.claude/skills/parallel-feature-analysis/SKILL.md)
- [`/design-retriever-fusion` skill](../../.claude/skills/design-retriever-fusion/SKILL.md)
- [CLAUDE.md - V2 Agentic Workflows](../../CLAUDE.md#09---roadmap-v1--v5-with-strategic-features)
- [ADR-0001: Modular Architecture](../../docs/adr/0001-modular-architecture.md)
