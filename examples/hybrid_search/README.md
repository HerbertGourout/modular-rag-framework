# hybrid_search — Retrieval Comparison Code Sample

> **Current status: not runnable without a code fix.** `main.py` still reads
> `HybridRetriever._bm25`, while the implementation now stores the lexical leg in `_lexical`.
> In addition, the documented `ingest` and `search` commands start separate processes, so the
> local preset's in-memory BM25 index is lost before search. Use
> `examples/simple_qa/first_query.py` for a working hybrid pipeline today.

This example shows what hybrid retrieval actually buys you: it runs the same
query through the vector-only, BM25-only, and RRF-fused hybrid retriever from
the `local-hybrid-rag` preset, and prints all three result sets side by side.

Unlike `examples/simple_qa/`, this example never calls a generator — it only
exercises retrieval, so **no LLM API key is required**, only Qdrant.

## Prerequisites

1. Python 3.11+
2. Docker (Qdrant)

## Setup

```bash
# From the repository root
cd modular-rag-framework
pip install -e ".[v1]"

# Start Qdrant
docker run -d -p 6333:6333 qdrant/qdrant
```

## Intended flow (currently blocked by the limitation above)

### Ingest documents

```bash
python examples/hybrid_search/main.py ingest examples/hybrid_search/docs/
```

Sample documents are provided in `docs/` — short pieces about vector search,
BM25, and RRF fusion itself, chosen so that a keyword-heavy query and a
semantic query surface different top results.

### Compare retrieval methods

```bash
# A keyword-heavy query — BM25 should do well
python examples/hybrid_search/main.py search "BM25 term frequency inverse document frequency"

# A paraphrased, conceptual query — vector search should do well
python examples/hybrid_search/main.py search "how to find documents that mean the same thing but use different words"
```

Intended output shape after the example is repaired:

```
Query: BM25 term frequency inverse document frequency

Vector-only (semantic) (top 5):
  #1  score=0.812  bm25-search.md
       BM25 (Best Matching 25) is a probabilistic ranking function built on term...
  ...

BM25-only (lexical) (top 5):
  #1  score=4.213  bm25-search.md
       ...
  ...

Hybrid (RRF-fused) (top 5):
  #1  score=0.0328  bm25-search.md
       ...
  ...
```

## What this demonstrates

| Feature | How it's used |
|---|---|
| **Manifest-driven config** | Same `manifests/presets/local-hybrid-rag.yaml` as `simple_qa` |
| **Retrieval-only pipeline usage** | `pipeline.retrieve()` — no generator, no LLM key |
| **Weighted RRF fusion** | `vector_weight` / `bm25_weight` from the manifest actually scale the fusion, not just cosmetic config |
| **Side-by-side method comparison** | Vector vs. BM25 vs. fused results for the same query |

## Extending

- Once repaired, tune the fusion balance by changing `retriever.config.vector_weight` /
  `bm25_weight` in a copied manifest and re-running the comparison in one process.
- Add your own documents to `docs/` to see hybrid retrieval on your own
  corpus.
