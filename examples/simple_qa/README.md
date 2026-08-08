# simple_qa — End-to-end RAG Example

This example shows the minimal path from documents to answers using the
`local-hybrid-rag` preset (adaptive chunking, hybrid retrieval, GPT-4o-mini).

## Prerequisites

1. Python 3.11+
2. Docker (Qdrant)
3. OpenAI API key

## Setup

```bash
# From the repository root
cd modular-rag-framework
pip install -e ".[v1]"

# Set your API key (the OpenAI SDK's own standard var — MRAG_OPENAI_API_KEY was
# declared in app/settings.py's Settings class, orphaned and deleted in Étape 8 of ADR-0007)
export OPENAI_API_KEY="sk-..."

# Start Qdrant
docker run -d -p 6333:6333 qdrant/qdrant
```

## Run

### Recommended: one-process hybrid run

```bash
python examples/simple_qa/first_query.py
```

This ingests the sample documents and asks a question before the in-memory BM25 index is lost.
Sample documents are provided in `docs/`.

### CLI compatibility path

```bash
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
python examples/simple_qa/main.py ask "What is Retrieval-Augmented Generation?"
```

The second command is a new process: Qdrant vectors persist, but the reference BM25 index does
not. It therefore demonstrates vector fallback, not full hybrid fusion. Use `first_query.py` for
the complete hybrid path.

Expected output:

```
Question: What is Retrieval-Augmented Generation?

Answer:
Retrieval-Augmented Generation (RAG) is a technique that combines information
retrieval with generative language models. Instead of relying solely on the
model's parametric knowledge, RAG retrieves relevant documents from an external
corpus and uses them as context for generation...

Citations:
  [1] rag-overview.md — score: 0.934
       "RAG was introduced by Lewis et al. (2020) and combines dense retrieval with..."
  [2] retrieval-methods.md — score: 0.891
       "BM25 and dense vector search are the two most common retrieval approaches..."
```

## What this demonstrates

| Feature | How it's used |
|---|---|
| **Manifest-driven config** | `manifests/presets/local-hybrid-rag.yaml` |
| **Adaptive chunking** | Section-aware splitting, 512-token max |
| **Hybrid retrieval** | Vector (Qdrant) + BM25 fused via RRF in `first_query.py` |
| **Cross-encoder reranking** | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **Grounded generation** | GPT-4o-mini with numbered source context |

The local preset deliberately does not configure a security guard, telemetry sink, tenant
policy, or audit sink. Use `secure-enterprise-rag.yaml` for those control-plane components.

## Extending

- Swap the generator: change `generator.type` in the manifest to `anthropic`.
- Adjust retrieval depth: change `retriever.config.k` from `20` to `50`.
- Enable the security guard: set `security.config.max_query_length: 2000`.
- Run the REST API: `create_app()` requires a manifest path argument, so bare `--factory` mode
  doesn't work — see [docs/api/rest.md](../../docs/api/rest.md) for the one-line wrapper pattern
  (`docker/server.py` is a working example), then `uvicorn server:app --reload`.
