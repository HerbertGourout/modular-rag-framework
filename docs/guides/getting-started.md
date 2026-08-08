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
`MRAG_OPENAI_API_KEY`. `app/settings.py`'s `Settings` class once declared `MRAG_`-prefixed
variables, but every adapter is built only from the manifest's own config — nothing in the
pipeline-wiring path ever constructed a `Settings()`, so `MRAG_OPENAI_API_KEY` never had any
effect (found in Lot 16c, `docs/refactoring/lot-16c-deployment-runbooks.md`), and the file was
deleted outright in Étape 8 of the ADR-0007 stabilization pass. `OpenAIGenerator` passes
`api_key=None` to the SDK when the manifest doesn't set one explicitly, and the SDK itself falls
back to plain `OPENAI_API_KEY`.

## Step 3 — Run a genuinely hybrid query in one process

BM25 is an in-memory reference index; Qdrant is persistent. To exercise both halves of hybrid
retrieval on a first run, ingestion and questioning must use the same application process:

```python
from modular_rag.app.bootstrap import load_application
from modular_rag.app.public import ingest_directory

application = load_application("manifests/presets/local-hybrid-rag.yaml")
try:
    chunks = ingest_directory("examples/simple_qa/docs", application.chunker)
    print(f"Indexed {application.ingest_chunks(chunks)} chunks")
    answer = application.answer("What is RAG?")
    print(answer.text)
    for citation in answer.citations:
        print(f"- {citation.source}: {citation.score:.3f}")
finally:
    application.close()
```

Save this as `first_query.py`, then run `python first_query.py`.

## Step 4 — Use the CLI

```bash
mrag ingest ./my_docs/ --manifest manifests/presets/local-hybrid-rag.yaml
```

The ingestion command:
1. Parses every `.txt`, `.md`, `.pdf` file under `./my_docs/`.
2. Normalizes and enriches each document.
3. Chunks using the adaptive chunker (512-token sections).
4. Generates embeddings using `bge-small-en-v1.5`.
5. Indexes chunks into Qdrant and builds an in-memory BM25 index for that command process.

Ask from a separate CLI invocation:

```bash
mrag ask "What are the main findings in the Q3 report?" \
         --manifest manifests/presets/local-hybrid-rag.yaml
```

Because this is a new process, its BM25 index starts empty and `HybridRetriever` falls back to
the persistent Qdrant/vector side. This is supported, but it is not a full hybrid query. Use the
single-process example above for hybrid behavior, or replace BM25 with a shared lexical backend
before deploying multiple workers.

Typical output:

```
Answer: The main findings in the Q3 report are...

Citations:
  [1] Q3-report.pdf (score: 0.92, page: 4)
      "Revenue grew 12% year-over-year, driven by..."
  [2] Q3-summary.md (score: 0.87, page: -)
      "Key highlights include a 15% reduction in operational costs..."
```

## Step 5 — Use the Python API after content is persisted

```python
from modular_rag.app.bootstrap import load_application

application = load_application("manifests/presets/local-hybrid-rag.yaml")
answer = application.answer("What are the main findings in the Q3 report?")

print(answer.text)
for cit in answer.citations:
    print(f"  [{cit.source}] {cit.passage[:80]}...")
application.close()
```

## Choosing a manifest

All files under `manifests/presets/` validate and wire; design-only configurations live under
`manifests/blueprints/`. See [`manifests/README.md`](../../manifests/README.md) for the
authoritative classification and runtime prerequisites.

| Preset | Status | Use case |
|---|---|---|
| `local-hybrid-rag.yaml` | **Runnable** | Local development, no auth, GPT-4o-mini — the reference starting point |
| `secure-enterprise-rag.yaml` | **Runnable** (V2) | Enterprise deployment — tenant isolation, PII redaction, inline policy engine, durable Postgres audit trail, blocking quality gate. Needs `QDRANT_URL`/`QDRANT_API_KEY`/`AUDIT_DATABASE_URL` set. |
| `langgraph-rag.yaml` | **Runnable** (V2) | Complex multi-step questions routed through `engine.adapter: langgraph` — a real `LangGraphEngineAdapter`, not native agents. Renamed from `agentic-rag.yaml`. |
| `manifests/blueprints/graph-memory-rag.yaml` | Blueprint | Entity-relationship reasoning — GraphRAG traversal is delegated per ADR-0005/0006 and not provided by the selected engine yet |
| `manifests/blueprints/multimodal-rag.yaml` | Blueprint | PDF with charts, images, tables — `embedder.type: multimodal` isn't a registered factory; VLM execution is delegated |

## Next steps

- [Plugin development guide](plugin-development.md) — add a custom chunker, retriever, or generator.
- [Observability guide](observability.md) — read traces, connect to monitoring.
- [Deployment guide](deployment.md) — run the REST API in production.
