---
name: optimize-chunking
description: Workflow for analyzing and optimizing document chunking for better retrieval quality
---

# Optimize Chunking Skill

_Originally authored as a workflow for `ingestion-specialist`, invoked as `/optimize-chunking`._


Systematic workflow for analyzing corpus characteristics and optimizing chunking strategy.

## When to Use

- Document retrieval performance is poor
- Chunk quality metrics are low
- Implementing new document type support
- Baseline performance establishing
- Corpus characteristics changing

## Workflow Steps

### 1. Analyze Corpus (15 min)

**Gather statistics:**

```python
from pathlib import Path
import statistics

def analyze_corpus(docs_path: str) -> dict:
    """Analyze corpus characteristics."""
    
    document_lengths = []
    sentence_counts = []
    document_types = {}
    
    for doc_path in Path(docs_path).glob("**/*"):
        if doc_path.is_file():
            text = doc_path.read_text()
            
            document_lengths.append(len(text))
            sentences = text.split(".")
            sentence_counts.append(len(sentences))
            doc_type = doc_path.suffix
            document_types[doc_type] = document_types.get(doc_type, 0) + 1
    
    return {
        "total_documents": len(document_lengths),
        "avg_doc_length": statistics.mean(document_lengths),
        "min_doc_length": min(document_lengths),
        "max_doc_length": max(document_lengths),
        "avg_sentences": statistics.mean(sentence_counts),
        "document_types": document_types
    }

# Run analysis
stats = analyze_corpus("examples/simple_qa/docs/")
print(f"Total docs: {stats['total_documents']}")
print(f"Avg length: {stats['avg_doc_length']} chars")
print(f"Max length: {stats['max_doc_length']} chars")
```

**Key metrics to collect:**
- Document count and sizes
- Sentence/paragraph lengths
- Document types (PDF, Markdown, text)
- Special structures (tables, code, lists)

### 2. Test Multiple Strategies (30 min)

**Create benchmark:**

```python
import pytest
from modular_rag.ingestion.chunkers import FixedChunker, SemanticChunker
from modular_rag.eval.metrics import compute_retrieval_quality

CHUNK_SIZES = [128, 256, 512, 1024]
STRATEGIES = [
    ("fixed_50_overlap", FixedChunker(512, overlap=50)),
    ("fixed_100_overlap", FixedChunker(512, overlap=100)),
    ("semantic", SemanticChunker()),
]

def benchmark_chunking(docs: list[str], queries: list[str]):
    """Benchmark different chunking strategies."""
    
    results = {}
    
    for strategy_name, chunker in STRATEGIES:
        # 1. Chunk documents
        chunks = []
        for doc in docs:
            chunks.extend(chunker.chunk(doc))
        
        # 2. Embed chunks
        embeddings = embed_batch(chunks)
        
        # 3. Create index
        vector_store = VectorStoreInMemory(embeddings)
        retriever = VectorRetriever(vector_store=vector_store)
        
        # 4. Test retrieval quality
        scores = []
        for query in queries:
            results = retriever.retrieve(query, k=10)
            score = compute_retrieval_quality(results, ground_truth)
            scores.append(score)
        
        results[strategy_name] = {
            "avg_quality": statistics.mean(scores),
            "chunk_count": len(chunks),
            "avg_chunk_size": statistics.mean(len(c) for c in chunks)
        }
    
    return results

# Run benchmark
benchmark_results = benchmark_chunking(documents, test_queries)

# Print results
for strategy, metrics in benchmark_results.items():
    print(f"{strategy}:")
    print(f"  Quality: {metrics['avg_quality']:.3f}")
    print(f"  Chunks: {metrics['chunk_count']}")
    print(f"  Avg size: {metrics['avg_chunk_size']:.0f} chars")
```

**Metrics to compare:**
- Retrieval quality (NDCG, MRR, F1)
- Chunk count
- Average chunk size
- Retrieval latency
- Memory usage

### 3. Analyze Results (10 min)

**Create comparison table:**

| Strategy | Quality | Chunks | Latency | Memory |
|----------|---------|--------|---------|--------|
| Fixed 256 | 0.72 | 1200 | 45ms | 12MB |
| Fixed 512 | **0.85** | 600 | **38ms** | **8MB** |
| Semantic | 0.88 | 550 | 120ms | 15MB |

**Decision criteria:**
- Quality: Is NDCG@10 > 0.8?
- Speed: Is retrieval < 100ms?
- Memory: Is overhead < 20MB?

### 4. Test with Real Queries (15 min)

**Create golden set:**

```python
GOLDEN_SET = [
    {
        "query": "What is RAG?",
        "relevant_docs": ["doc_1.pdf", "doc_3.md"],
        "answer": "RAG combines retrieval and generation"
    },
    {
        "query": "How does vector search work?",
        "relevant_docs": ["doc_2.pdf"],
        "answer": "Vector search uses embeddings..."
    },
    # ... more queries
]

def test_chunking_with_golden_set(chunker, retriever):
    """Validate chunking with golden queries."""
    
    results = []
    for test in GOLDEN_SET:
        query = test["query"]
        expected_docs = test["relevant_docs"]
        
        retrieved = retriever.retrieve(query, k=5)
        retrieved_ids = [r.doc_id for r in retrieved]
        
        # Calculate recall
        matches = sum(1 for doc in expected_docs if doc in retrieved_ids)
        recall = matches / len(expected_docs)
        
        results.append({
            "query": query,
            "recall": recall,
            "precision": matches / len(retrieved_ids)
        })
    
    avg_recall = statistics.mean(r["recall"] for r in results)
    print(f"Average recall: {avg_recall:.2%}")
    
    assert avg_recall > 0.8, "Chunking strategy not meeting recall target"
```

### 5. Optimize Overlap (10 min)

**Overlap strategies:**

```python
# Test different overlaps
OVERLAPS = [0, 50, 100, 150]

for overlap in OVERLAPS:
    chunker = FixedChunker(chunk_size=512, overlap=overlap)
    chunks = []
    for doc in documents:
        chunks.extend(chunker.chunk(doc))
    
    # Measure redundancy
    unique_chunks = len(set(chunks))
    redundancy = (len(chunks) - unique_chunks) / len(chunks)
    
    print(f"Overlap {overlap}: {redundancy:.1%} redundancy")

# Recommendation: balance between context preservation (high overlap)
# and storage efficiency (low overlap)
# Typical: 50-100 char overlap for 512 char chunks
```

### 6. Document-Specific Optimization (15 min)

**Domain-specific chunking:**

```python
def chunk_code_file(code_text: str) -> list[str]:
    """Chunk code by function/class."""
    # Split on function definitions
    chunks = []
    current_chunk = []
    
    for line in code_text.split("\n"):
        if line.startswith("def ") or line.startswith("class "):
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            current_chunk = [line]
        else:
            current_chunk.append(line)
    
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks

def chunk_markdown_file(md_text: str) -> list[str]:
    """Chunk Markdown by heading."""
    chunks = []
    current_chunk = []
    
    for line in md_text.split("\n"):
        if line.startswith("##"):
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            current_chunk = [line]
        else:
            current_chunk.append(line)
    
    return chunks
```

### 7. Create Final Configuration (5 min)

**Update manifest:**

```yaml
# manifests/presets/optimized-rag.yaml
version: 1.0

ingestion:
  chunker:
    type: fixed
    chunk_size: 512          # Determined by analysis
    overlap: 75              # Determined by testing
    
# Optional: domain-specific chunker
  specialized_chunkers:
    - type: code_chunker
      for_extensions: [.py, .js, .java]
    - type: markdown_chunker
      for_extensions: [.md]
```

### 8. Document Recommendations (5 min)

**Create ADR if significant:**

```markdown
# ADR: Optimize Chunking Strategy

## Context
Analyzed corpus of {{total}} documents.
- Average document size: {{avg_size}} chars
- Document types: {{types}}

## Decision
Use Fixed chunking (512 chars) with 75-char overlap for general documents.
Use specialized chunkers for code and Markdown.

## Results
- Retrieval quality: NDCG@10 = 0.85
- Retrieval latency: 38ms (95th percentile)
- Memory overhead: 8MB per 1M chunks

## Rationale
Trade-off analysis:
- Semantic chunking more accurate (0.88 vs 0.85)
- But 3x slower (120ms vs 38ms)
- Fixed chunking meets quality target with better performance

## Next Steps
- Monitor quality in production
- Adjust if new document types added
```

## Optimization Decision Tree

```
Corpus analysis
    ↓
[Is retrieval quality > 0.8?]
    ├─ YES → Good! Monitor for regressions
    └─ NO → Test alternative chunk sizes
            ↓
        [Test sizes: 256, 512, 1024]
            ├─ None work → Try semantic chunking
            ├─ One works → Use it, optimize overlap
            └─ Multiple work → Choose smallest (less storage)
```

## Common Issues & Fixes

| Problem | Cause | Solution |
|---------|-------|----------|
| Poor retrieval | Chunks too small | Increase chunk size |
| | Chunks too large | Decrease chunk size |
| | Missing overlap | Add 50-100 char overlap |
| Memory bloat | Too many chunks | Increase chunk size |
| Latency high | Vector DB inefficient | Index optimization, not chunking |

## Success Criteria

✅ Retrieval quality (NDCG@10) > 0.8
✅ Retrieval latency < 100ms
✅ Memory overhead reasonable
✅ Tested with golden set
✅ Domain-specific strategies applied
✅ Configuration documented
✅ Performance baseline established

## Time Estimate

**Total:** 1.5-2 hours including analysis, testing, and optimization
