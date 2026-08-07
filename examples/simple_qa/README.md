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

# Set your API key (the OpenAI SDK's own standard var — MRAG_OPENAI_API_KEY is
# declared in app/settings.py but never read in the real pipeline-wiring path)
export OPENAI_API_KEY="sk-..."

# Start Qdrant
docker run -d -p 6333:6333 qdrant/qdrant
```

## Run

### Ingest documents

```bash
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
```

Sample documents are provided in `docs/` — a short text about RAG and retrieval methods.

### Ask a question

```bash
python examples/simple_qa/main.py ask "What is Retrieval-Augmented Generation?"
```

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
| **Hybrid retrieval** | Vector (Qdrant) + BM25 fused via RRF |
| **Cross-encoder reranking** | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **Grounded generation** | GPT-4o-mini with numbered source context |
| **Security guard** | Query length + injection check |
| **Structured telemetry** | Trace written to stdout as JSON |

## Extending

- Swap the generator: change `generator.type` in the manifest to `anthropic`.
- Adjust retrieval depth: change `retriever.config.k` from `20` to `50`.
- Enable the security guard: set `security.config.max_query_length: 2000`.
- Run the REST API: `create_app()` requires a manifest path argument, so bare `--factory` mode
  doesn't work — see [docs/api/rest.md](../../docs/api/rest.md) for the one-line wrapper pattern
  (`docker/server.py` is a working example), then `uvicorn server:app --reload`.
