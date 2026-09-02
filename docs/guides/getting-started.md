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
`MRAG_OPENAI_API_KEY`.

- Every adapter is built only from the manifest's own config. Nothing in the pipeline-wiring path
  ever constructs a `Settings()` object.
- `MRAG_OPENAI_API_KEY` never had any effect (found in Lot 16c,
  `docs/refactoring/lot-16c-deployment-runbooks.md`). The `Settings` class that once declared it
  was deleted outright in Étape 8 of the ADR-0007 stabilization pass.
- `OpenAIGenerator` passes `api_key=None` to the SDK when the manifest doesn't set one explicitly.
  The SDK itself then falls back to plain `OPENAI_API_KEY`.

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
1. Parses every `.txt`, `.md`, `.pdf`, `.docx` and `.html` file under `./my_docs/`.
2. Normalizes and enriches each document, including a contextual `embedding_text` used only for
   embedding while the original content remains available for citations.
3. Chunks using the adaptive chunker (512-token sections).
4. Generates embeddings using `bge-small-en-v1.5`.
5. Indexes chunks into Qdrant and builds an in-memory BM25 index for that command process.

Ask from a separate CLI invocation:

```bash
mrag ask "What are the main findings in the Q3 report?" \
         --manifest manifests/presets/local-hybrid-rag.yaml
```

Because this is a new process, and `local-hybrid-rag.yaml` uses the default `lexical:
bm25-memory` backend, its BM25 index starts empty. `HybridRetriever` falls back to the
persistent Qdrant/vector side — supported, but not a full hybrid query.

Two ways to get real hybrid behavior:
- Use the single-process example from Step 3 above.
- Select `lexical: sparse-qdrant` in the manifest before deploying multiple workers. This is a
  built-in persistent lexical backend — you don't need to supply your own (see
  `manifests/presets/secure-enterprise-rag.yaml`; requires Qdrant client/server 1.10+).

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
| `secure-enterprise-rag.yaml` | **Runnable** (V2, native) | Tenant isolation, PII redaction, inline policy engine, durable Postgres audit/feedback/human-review storage, persistent sparse retrieval, and telemetry. Offline regression/drift jobs run separately. Needs `QDRANT_URL`/`QDRANT_API_KEY`/`AUDIT_DATABASE_URL`, reachable Qdrant/Postgres, and API token verification for HTTP use. This does not yet enforce Lot 20 provider-egress policy. |
| `langgraph-rag.yaml` | **Runnable** (V2) | Questions routed through a real but fixed route → retrieve → guard → generate `LangGraphEngineAdapter`. It does not currently provide planning, tools, decomposition or collaborating agents. |

The LangGraph preset is not a wrapper for an existing LangChain/LangGraph application. That
bring-your-own-application path is planned by accepted ADR-0015 and has no runnable manifest today.
| `manifests/blueprints/graph-memory-rag.yaml` | Blueprint | Entity-relationship reasoning — GraphRAG traversal is delegated per ADR-0005/0006 and not provided by the selected engine yet |
| `manifests/blueprints/multimodal-rag.yaml` | Blueprint | PDF with charts, images, tables — `embedder.type: multimodal` isn't a registered factory; VLM execution is delegated |

## Next steps

- [Plugin development guide](plugin-development.md) — add a custom chunker, retriever, or generator.
- [Observability guide](observability.md) — understand traces, live spans and operational metrics,
  including the current gauge limitations before connecting alerts.
- [Deployment guide](deployment.md) — run the REST API in production.
