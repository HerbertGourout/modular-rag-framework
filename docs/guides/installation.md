# Installation

This guide gets the framework installed and importable on your machine. It does not walk
through running a real query end to end — for that, see
[getting-started.md](getting-started.md) once installation succeeds. The two guides are
split deliberately: installation problems (missing Python version, wrong dependency group)
are a different failure mode than pipeline problems (wrong manifest, missing API key), and
conflating them makes troubleshooting slower.

## Requirements

- Python 3.11 or later
- Git
- Access to at least one LLM backend (OpenAI, Azure OpenAI, or Anthropic)
- Optional: Docker (for Qdrant vector store)

## Development installation

Clone the repository and install in editable mode:

```bash
git clone https://github.com/HerbertGourout/modular-rag-framework.git
cd modular-rag-framework
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -e ".[v1,dev]"
```

## Extras

The project uses optional dependency groups rather than one flat dependency list. This
matters in practice: `sentence-transformers` alone pulls in a multi-gigabyte PyTorch install,
and `neo4j`/`spacy` (V3) are irrelevant if you only ever run V1 pipelines. Installing only
the group your work actually needs keeps setup fast and avoids dragging heavy, unused
dependencies into a CI image or a client's production container. Install only what you need:

| Group | Install command | What it adds |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | Core RAG: fastapi, uvicorn, typer, pymupdf, python-docx, beautifulsoup4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, cohere, tiktoken |
| `v4` | `pip install -e ".[v4]"` | Observability: opentelemetry-sdk/api/exporter-otlp — not yet wired into any code (V4 not reached), declared ahead of that work |
| `v5` | `pip install -e ".[v5]"` | Multimodal: pymupdf (already in `v1`), pillow, pytesseract — not yet wired into any code (V5 not reached) |
| `langgraph` | `pip install -e ".[langgraph]"` | The external `DocumentEngine` adapter (Lot 15) — only needed if a manifest sets `engine.adapter: "langgraph"` |
| `supply-chain` | `pip install -e ".[supply-chain]"` | `pip-audit`, `pip-licenses`, `cyclonedx-bom` — CI/audit tooling (Lot 16b), not needed to run the framework |
| `dev` | `pip install -e ".[dev]"` | Testing and linting: pytest, pytest-asyncio, pytest-cov, mypy, ruff, httpx, respx, build |
| `all` | `pip install -e ".[all]"` | `v1` + `v4` + `v5` + `langgraph` + `dev` (not `supply-chain` — opt-in audit tooling, see above) |

There is no `v3` (Graph Memory) group — removed in Lot 17 (`docs/refactoring-plan.md`): its
dependencies (neo4j, networkx, spacy, python-louvain) were never imported anywhere in
`src/modular_rag/`, and backed the native GraphRAG build that
[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2 now delegates to the
selected external engine instead.

## Running Qdrant locally (V1)

Qdrant is the default vector store for V1 — it holds the dense embeddings that power the
"vector" half of hybrid retrieval (the BM25 half is an in-memory index that needs no
service). Unlike the framework's Python code, Qdrant is an external service that must be
running before you ingest or query anything; forgetting this step is the most common reason
`mrag ingest` fails on a first run. Start it with Docker:

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Or add it to a `docker-compose.yml`:

```yaml
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant_data:/qdrant/storage
```

The default manifest (`manifests/presets/local-hybrid-rag.yaml`) connects to `localhost:6333`.

## Environment variables

`app/settings.py` declares a `pydantic-settings` model (`Settings`) with these `MRAG_`-prefixed
fields, but **it's orphaned**: nothing in the real pipeline-wiring path
(`orchestration/_default_factories.py`, `app/bootstrap.py`) ever constructs `Settings()` or
calls `get_settings()`. Setting any variable in the table below has **no effect** on the
pipeline today. All real configuration goes through the manifest YAML instead — component
`config:` blocks are passed straight to each adapter's constructor (`**cfg.config`).

| Variable (declared, not read) | What actually works instead |
|---|---|
| `MRAG_OPENAI_API_KEY` / `MRAG_ANTHROPIC_API_KEY` | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — the SDKs' own standard names, read automatically when the manifest's `generator.config.api_key` is left unset |
| `MRAG_QDRANT_URL`, `MRAG_QDRANT_COLLECTION` | Set `url`/`collection` directly in the manifest's `indexer`/`retriever` `config:` block — there is no env-var fallback |
| `MRAG_EMBEDDING_MODEL` | Set `model_name`/equivalent directly in the manifest's `embedder.config:` block |
| `MRAG_ENVIRONMENT`, `MRAG_LOG_LEVEL` | No working equivalent today; these are aspirational fields for a future settings wiring pass |

Manifests are the source of truth for configuration (per [CLAUDE.md](../../CLAUDE.md) rule 03)
— see [manifests/README.md](../../manifests/README.md) for the Runnable
`local-hybrid-rag.yaml` preset as a starting template, and put secrets (API keys) in the
environment variable the underlying SDK actually reads, never a manifest committed to Git.

## Verifying the installation

```bash
mrag version
```

Expected output: `Modular RAG Framework vX.Y.Z`.

> At the current pre-alpha stage (`v0.0.x`), this command confirms the package is importable. Full end-to-end verification will be available at `v0.1` with `examples/simple_qa/`.
