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
| `v1` | `pip install -e ".[v1]"` | Core RAG: fastapi, uvicorn, typer, pymupdf, python-docx, beautifulsoup4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, tiktoken. `cohere` and `langchain-text-splitters` were removed here in Lot 9 (Codex review MEDIUM-004) — zero imports anywhere, no adapter class ever used either |
| `v4` | `pip install -e ".[v4]"` | Observability: opentelemetry-sdk/api/exporter-otlp — wired since [ADR-0012](../adr/0012-opentelemetry-tracing-port.md) (`observability.tracer.type: otel`, see `docs/guides/observability.md`); only required if a manifest selects that tracer type |
| `v5` | `pip install -e ".[v5]"` | Multimodal: pymupdf (already in `v1`), pillow, pytesseract — not yet wired into any code (V5 not reached) |
| `langgraph` | `pip install -e ".[langgraph]"` | The external `DocumentEngine` adapter (Lot 15) — only needed if a manifest sets `engine.adapter: "langgraph"` |
| `postgres` | `pip install -e ".[postgres]"` | `psycopg` driver for the durable audit and lifecycle components used by `secure-enterprise-rag.yaml` |
| `auth` | `pip install -e ".[auth]"` | PyJWT cryptography support for `KeycloakTokenVerifier` in authenticated API deployments |
| `supply-chain` | `pip install -e ".[supply-chain]"` | `pip-audit`, `pip-licenses`, `cyclonedx-bom` — CI/audit tooling (Lot 16b), not needed to run the framework |
| `dev` | `pip install -e ".[dev]"` | Testing and linting: pytest, pytest-asyncio, pytest-cov, mypy, ruff, httpx, respx, build |
| `all` | `pip install -e ".[all]"` | `v1` + `v4` + `v5` + `langgraph` + `postgres` + `auth` + `dev` (not `supply-chain`) |

Recommended installations by runnable preset:

| Preset | Command |
|---|---|
| `local-hybrid-rag.yaml` | `pip install -e ".[v1]"` |
| `langgraph-rag.yaml` | `pip install -e ".[v1,langgraph]"` |
| `secure-enterprise-rag.yaml` | `pip install -e ".[v1,postgres]"` |

There is no `v3` (Graph Memory) group — removed in Lot 17 (`docs/refactoring-plan.md`): its
dependencies (neo4j, networkx, spacy, python-louvain) were never imported anywhere in
`src/modular_rag/`, and backed the native GraphRAG build that
[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2 now delegates to the
selected external engine instead.

## Running Qdrant locally (V1)

Qdrant is the default vector store for V1 — it holds the dense embeddings that power the
"vector" half of hybrid retrieval. The lexical half's service requirement depends on which
backend the manifest's `retriever.config.lexical` key selects: `"bm25-memory"` (the local preset's
default) is an in-memory index that needs no service; `"sparse-qdrant"` (the enterprise/secure
preset's choice — see `manifests/presets/secure-enterprise-rag.yaml`) is a second, dedicated Qdrant
collection on the *same* Qdrant server, requiring client and server version **1.10+**
(`Modifier.IDF`/`query_points()` are not present in Qdrant client 1.9). Unlike the framework's
Python code, Qdrant is an external service that must be running before you ingest or query
anything; forgetting this step is the most common reason `mrag ingest` fails on a first run.
Start it with Docker (pin a version instead of `latest` in any deployment that needs
`sparse-qdrant`'s IDF support — `latest` is fine for `bm25-memory`-only local development):

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant:v1.10.0
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

There is no `MRAG_`-prefixed environment-variable convention in this codebase. A
`pydantic-settings` `Settings` model with `MRAG_*` fields once lived in `app/settings.py`, but it
was orphaned — nothing in the real pipeline-wiring path ever constructed `Settings()` or called
`get_settings()` — and the file was deleted outright in Étape 8 of the ADR-0007 stabilization
pass. All real configuration goes through the manifest YAML instead — component `config:` blocks
are passed straight to each adapter's constructor (`**cfg.config`).

| What you might expect | What actually works |
|---|---|
| `MRAG_OPENAI_API_KEY` / `MRAG_ANTHROPIC_API_KEY` | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — the SDKs' own standard names, read automatically when the manifest's `generator.config.api_key` is left unset |
| `MRAG_QDRANT_URL`, `MRAG_QDRANT_COLLECTION` | No implicit SDK fallback. Set `url`/`collection` in the manifest, or reference `${QDRANT_URL}`/`secret://QDRANT_API_KEY`; startup resolves those references before wiring. |
| `MRAG_EMBEDDING_MODEL` | Set `model_name`/equivalent directly in the manifest's `embedder.config:` block |
| `MRAG_ENVIRONMENT`, `MRAG_LOG_LEVEL` | No working equivalent today |

Manifests are the source of truth for configuration (per [CLAUDE.md](../../CLAUDE.md) rule 03)
— see [manifests/README.md](../../manifests/README.md) for the Runnable
`local-hybrid-rag.yaml` preset as a starting template, and put secrets (API keys) in the
environment variable the underlying SDK actually reads, never a manifest committed to Git.

## Verifying the installation

```bash
mrag version
```

Expected output: `modular-rag X.Y.Z` (e.g. `modular-rag 0.0.1`) — `cli/__init__.py`'s `version()`
command prints `f"modular-rag {__version__}"` directly, reading the same
`importlib.metadata.version("modular-rag")`-backed value everything else in the codebase does
(single source: `pyproject.toml`'s `[project].version`).

> At the current pre-alpha stage (`v0.0.x`), this command confirms the package is importable. Full end-to-end verification will be available at `v0.1` with `examples/simple_qa/`.
