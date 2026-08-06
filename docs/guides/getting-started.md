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
export OPENAI_API_KEY="sk-..."
```

Note the variable name: it's the OpenAI SDK's own standard `OPENAI_API_KEY`, **not**
`MRAG_OPENAI_API_KEY`. `app/settings.py`'s `Settings` class declares `MRAG_`-prefixed variables,
but nothing in the actual pipeline-wiring path (`orchestration/_default_factories.py`) ever
constructs a `Settings()` — every adapter is built only from the manifest's own config, so
`MRAG_OPENAI_API_KEY` has no effect. `OpenAIGenerator` passes `api_key=None` to the SDK when the
manifest doesn't set one explicitly, and the SDK itself falls back to plain `OPENAI_API_KEY`
(found in Lot 16c, `docs/refactoring/lot-16c-deployment-runbooks.md`).

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

Only `local-hybrid-rag.yaml` actually wires end to end today — every other preset below is
**Blueprint** (declared, but `ComponentRegistry.wire()` doesn't process every field it uses, or
references files/interpolation that don't resolve). See
[`manifests/README.md`](../../manifests/README.md) for the full, current classification and why.

| Preset | Status | Use case (once its blueprint is completed) |
|---|---|---|
| `local-hybrid-rag.yaml` | **Runnable** | Local development, no auth, GPT-4o-mini — the only one to actually run today |
| `secure-enterprise-rag.yaml` | Blueprint | Internal deployment, security guards enabled, GPT-4o |
| `agentic-rag.yaml` | Blueprint | Complex multi-step questions — planner/agents fields are unprocessed by `wire()`; this scope is delegated to an external engine per ADR-0005, not a native runtime to complete |
| `graph-memory-rag.yaml` | Blueprint | Entity-relationship reasoning — GraphRAG traversal is delegated per ADR-0005/0006 |
| `multimodal-rag.yaml` | Blueprint | PDF with charts, images, tables — `embedder.type: multimodal` isn't a registered factory, `wire()` raises immediately |

## Next steps

- [Plugin development guide](plugin-development.md) — add a custom chunker, retriever, or generator.
- [Observability guide](observability.md) — read traces, connect to monitoring.
- [Deployment guide](deployment.md) — run the REST API in production.
