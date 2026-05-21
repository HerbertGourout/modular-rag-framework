# Getting Started

This guide walks you from a fresh clone to a working RAG query using the `local-hybrid-rag` preset.

## Prerequisites

- Python 3.11+
- Docker (for Qdrant)
- OpenAI API key (or Anthropic)

Install the framework first — see [installation.md](installation.md).

## Step 1 — Start Qdrant

```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

## Step 2 — Set your API key

```bash
export MRAG_OPENAI_API_KEY="sk-..."
```

## Step 3 — Ingest documents

```bash
mrag ingest ./my_docs/ --manifest manifests/presets/local-hybrid-rag.yaml
```

This command:
1. Parses every `.txt`, `.md`, `.pdf` file under `./my_docs/`.
2. Normalizes and enriches each document.
3. Chunks using the adaptive chunker (512-token sections).
4. Generates embeddings using `bge-small-en-v1.5`.
5. Indexes chunks into Qdrant and builds an in-memory BM25 index.

## Step 4 — Ask a question

```bash
mrag ask "What are the main findings in the Q3 report?" \
         --manifest manifests/presets/local-hybrid-rag.yaml
```

Output:

```
Answer: The main findings in the Q3 report are...

Citations:
  [1] Q3-report.pdf (score: 0.92, page: 4)
      "Revenue grew 12% year-over-year, driven by..."
  [2] Q3-summary.md (score: 0.87, page: -)
      "Key highlights include a 15% reduction in operational costs..."
```

## Step 5 — Use the Python API

```python
from modular_rag.app.bootstrap import load_pipeline

pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
answer = pipeline.answer("What are the main findings in the Q3 report?")

print(answer.text)
for cit in answer.citations:
    print(f"  [{cit.source}] {cit.passage[:80]}...")
```

## Choosing a manifest

| Preset | Use case |
|---|---|
| `local-hybrid-rag.yaml` | Local development, no auth, GPT-4o-mini |
| `secure-enterprise-rag.yaml` | Internal deployment, security guards enabled, GPT-4o |
| `agentic-rag.yaml` | Complex multi-step questions, 5-agent runtime (V2) |
| `graph-memory-rag.yaml` | Entity-relationship reasoning, GraphRAG (V3) |
| `multimodal-rag.yaml` | PDF with charts, images, tables (V5) |

## Next steps

- [Plugin development guide](plugin-development.md) — add a custom chunker, retriever, or generator.
- [Observability guide](observability.md) — read traces, connect to monitoring.
- [Deployment guide](deployment.md) — run the REST API in production.
