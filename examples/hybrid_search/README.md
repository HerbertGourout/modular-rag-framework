# hybrid_search — Retrieval Comparison Example

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

## Run

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

Expected output shape:

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

- Tune the fusion balance: change `retriever.config.vector_weight` /
  `bm25_weight` in the manifest and re-run `search` to see the ranking shift.
- Add your own documents to `docs/` to see hybrid retrieval on your own
  corpus.
