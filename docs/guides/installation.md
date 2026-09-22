# Installation

This guide gets the framework installed and importable on your machine. It does not walk
through running a real query end to end — for that, see
[getting-started.md](getting-started.md) once installation succeeds.

The two guides are split deliberately. Installation problems (missing Python version, wrong
dependency group) are a different failure mode than pipeline problems (wrong manifest, missing
API key). Conflating them makes troubleshooting slower.

## Clean-room checklist

Run these in order from a clean workstation. Every command runs from the repository root unless
stated otherwise, and each step has an observable success condition. If one fails, fix it before
moving on — later steps assume the earlier ones passed.

| # | Step | Needs | You should see | If it fails |
|---|---|---|---|---|
| 1 | `python --version` | Python 3.11+ on `PATH` | `Python 3.11.x` or later | Install Python 3.11+; on Windows re-run the installer with "Add to PATH" |
| 2 | `git --version` | Git | Any version string | Install Git |
| 3 | `python -m venv .venv` | Step 1 | A `.venv` directory exists | Nothing to activate yet — every command below calls the interpreter inside it by path |
| 4 | `.venv\Scripts\python.exe -m pip install -e ".[v1,v4,langgraph,dev]"` (Windows) or `.venv/bin/python -m pip install -e ".[v1,v4,langgraph,dev]"` | Step 3, network access | `Successfully installed modular-rag-…` | Quote the extras — some shells expand the brackets — and keep this set, the one CI installs for its test jobs |
| 5 | `.venv\Scripts\mrag.exe version` or `.venv/bin/mrag version` | Step 4 | `modular-rag 0.0.1` | The editable install did not finish; re-run step 4 |
| 6 | `.venv\Scripts\python.exe -m pytest tests/unit tests/contract -q` or `.venv/bin/python -m pytest tests/unit tests/contract -q` | Step 4 only — **no service, no key** | All tests pass | A missing-module error means step 4 installed fewer extras; otherwise it is a real problem, not a setup gap |
| 7 | `.venv\Scripts\python.exe scripts/check_layering.py` or `.venv/bin/python scripts/check_layering.py` | Step 4 | `Layering check passed.` | Report it: on a clean checkout this never fails |
| 8 | Start Qdrant (below) | Docker | `curl http://localhost:6333/healthz` returns `healthz check passed` | Docker is not running, or port 6333 is taken — see [troubleshooting.md](troubleshooting.md) |
| 9 | Export `OPENAI_API_KEY` (below) | An OpenAI account for the shipped walkthrough | A presence check reports it is set — never print the value | Set it in the same shell you will run from; steps 6 and 7 never need it |
| 10 | First query | Steps 8 and 9, plus access to the Hugging Face model registry on first run | A sourced answer, per [getting-started.md](getting-started.md) | Follow that guide's own recovery notes |

Steps 1 to 7 are the deterministic part: they need no external service and no paid credential.
Steps 8 to 10 are the ones that reach outside your machine.

**On activation.** The checklist deliberately never activates the environment: calling
`.venv\Scripts\python.exe` (or `.venv/bin/python`) works identically in PowerShell, `cmd.exe`,
Bash and zsh. If you prefer an activated shell, use the line for yours — and note that
PowerShell refuses `.venv\Scripts\Activate.ps1` when script execution is disabled, which is a
policy setting, not a broken install:

```powershell
# one-off, for this process only
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**On extras.** `.[v1,dev]` is enough to *run* the framework with the local preset, but not to run
the full unit and contract suites: they exercise the real LangGraph adapter and the OpenTelemetry
tracer, which live in the `langgraph` and `v4` extras. The CI test jobs install
`.[v1,v4,langgraph,dev]` for that reason, and step 4 matches them.

## Requirements

- Python 3.11 or later
- Git
- Access to OpenAI or Anthropic for LLM-backed runs (the deterministic test generator needs none)
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

The project uses optional dependency groups rather than one flat dependency list.

This matters in practice: `sentence-transformers` alone pulls in a multi-gigabyte PyTorch
install, and `neo4j`/`spacy` (V3) are irrelevant if you only ever run V1 pipelines. Installing
only the group your work actually needs keeps setup fast, and avoids dragging heavy, unused
dependencies into a CI image or a client's production container.

Install only what you need:

| Group | Install command | What it adds |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | Core RAG: fastapi, uvicorn, typer, pymupdf, python-docx, beautifulsoup4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, tiktoken. `cohere` and `langchain-text-splitters` were removed here in Lot 9 (Codex review MEDIUM-004) — zero imports anywhere, no adapter class ever used either |
| `v4` | `pip install -e ".[v4]"` | Observability: opentelemetry-sdk/api/exporter-otlp — backs both [ADR-0012](../adr/0012-opentelemetry-tracing-port.md) tracing (`observability.tracer.type: otel`) and ADR-0013 metrics (`observability.meter.type: otel`); required only when either role is selected |
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

There is no `v3` (Graph Memory) group — removed in Lot 17 (`docs/refactoring-plan.md`).

- Its dependencies (neo4j, networkx, spacy, python-louvain) were never imported anywhere in
  `src/modular_rag/`.
- They backed the native GraphRAG build that
  [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2 now delegates to the
  selected external engine instead.

## Running Qdrant locally (V1)

Qdrant is the default vector store for V1 — it holds the dense embeddings that power the
"vector" half of hybrid retrieval.

The lexical half's service requirement depends on which backend the manifest's
`retriever.config.lexical` key selects:
- `"bm25-memory"` (the local preset's default) — an in-memory index that needs no service.
- `"sparse-qdrant"` (the enterprise/secure preset's choice — see
  `manifests/presets/secure-enterprise-rag.yaml`) — a second, dedicated Qdrant collection on the
  *same* Qdrant server. Requires client and server version **1.10+** (`Modifier.IDF`/
  `query_points()` are not present in Qdrant client 1.9).

Unlike the framework's Python code, Qdrant is an external service that must be running before you
ingest or query anything. Forgetting this step is the most common reason `mrag ingest` fails on a
first run.

Start it with Docker. Pin a version instead of `latest` in any deployment that needs
`sparse-qdrant`'s IDF support — `latest` is fine for `bm25-memory`-only local development:

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

## Which runs need what

Not every command needs a service or a credential. Knowing which is which saves a pointless
Docker start — and prevents assuming a failure is your setup when it is not.

| Run | External service | Paid credential |
|---|---|---|
| `pytest tests/unit tests/contract` | None | None |
| `python scripts/check_layering.py`, `python scripts/check_docs.py` | None | None |
| `python scripts/run_benchmark.py` (offline golden set) | Qdrant — its manifest indexes into a `eval-benchmark-core-v1` collection | None — it wires the deterministic embedder and generator |
| `pytest tests/integration -m integration` | Qdrant, plus PostgreSQL for the full directory | None |
| `pytest tests/e2e/test_secure_preset_e2e.py -m e2e` | Qdrant and PostgreSQL | None — deterministic by design |
| `pytest tests/e2e/test_simple_qa_pipeline.py -m e2e` | Qdrant | Yes, a real LLM key |
| `mrag ingest` / `mrag ask` with `local-hybrid-rag.yaml` | Qdrant, plus the Hugging Face model registry on the first run | Yes, `OPENAI_API_KEY` — the preset wires `generator.type: openai` |

The first run of the local preset downloads two model artifacts it does not ship:
`BAAI/bge-small-en-v1.5` for embeddings and `cross-encoder/ms-marco-MiniLM-L-6-v2` for
reranking. Both are fetched lazily, on first use, not at install time. Behind a proxy, an
allow-list or an air-gap, pre-populate the Hugging Face cache on a connected machine and copy it
over, or point `HF_HOME` at an existing cache — otherwise the first query fails or stalls even
though every other prerequisite is met.

## Credentials for the first query

The shipped walkthrough uses `manifests/presets/local-hybrid-rag.yaml`, which selects the OpenAI
generator. Set the SDK's own variable in the shell you will run from:

```powershell
$env:OPENAI_API_KEY = "sk-..."        # PowerShell, current process
```

```bash
export OPENAI_API_KEY="sk-..."        # Bash / zsh
```

Check that it is set without printing it — terminal history, screen shares and log collectors
capture whatever you echo:

```powershell
if ($env:OPENAI_API_KEY) { "OPENAI_API_KEY is set" } else { "OPENAI_API_KEY is missing" }
```

```bash
[ -n "$OPENAI_API_KEY" ] && echo "OPENAI_API_KEY is set" || echo "OPENAI_API_KEY is missing"
```

To use Anthropic instead, copy the preset and make **three** edits, not one. Changing only the
generator type leaves an OpenAI model name behind and a manifest that startup rejects, because
every wired remote provider must appear in the egress policy:

```yaml
generator:
  type: anthropic
  config:
    model: "claude-opus-4-7"      # 1. an Anthropic model; the OpenAI name would be sent verbatim
    temperature: 0.1
    max_tokens: 2048

governance:
  egress_policy:
    type: manifest
    config:
      providers:
        sentence-transformers: {local: true}
        cross-encoder: {local: true}
        anthropic: {local: false, max_classification: restricted}   # 2. replaces the openai entry
```

Then set `ANTHROPIC_API_KEY` instead of `OPENAI_API_KEY` (3). Omitting `model` also works —
`AnthropicGenerator` defaults to `claude-opus-4-7` — but stating it keeps the manifest explicit.
This variant is not one of the shipped presets: validate it with
`mrag validate --manifest <your copy>` before relying on it.

> **`.env` is not loaded automatically.** Nothing in the package or its dependencies reads a
> dotenv file: configuration resolution reads `os.environ` directly. Docker Compose interpolates
> `.env` for its own workflows, and `scripts/smoke_test_compose.py` reads it explicitly, but
> `mrag` and plain Python runs see only what the process environment already holds. Source or
> export the values yourself.

## Local-only configuration and secrets

Keep credentials out of the repository. The rules that apply here:

- API keys live in your environment, under the SDK's own variable name, never in a manifest that
  is committed.
- A manifest may reference them indirectly with `${VAR}` or `secret://VAR`; startup resolves
  those before wiring.
- `.env`, `CLAUDE.local.md` and `.claude/settings.local.json` are ignored by Git and are the
  right place for machine-specific values. `.env.example` is the tracked template. Remember that
  `.env` reaches `mrag` only if you source or export it yourself (see above).
- Nothing in tracked documentation should contain a real key or a personal path.

## Environment variables

There is no `MRAG_`-prefixed environment-variable convention in this codebase.

A `pydantic-settings` `Settings` model with `MRAG_*` fields once lived in `app/settings.py`, but
it was orphaned: nothing in the real pipeline-wiring path ever constructed `Settings()` or called
`get_settings()`. The file was deleted outright in Étape 8 of the ADR-0007 stabilization pass.

All real configuration goes through the manifest YAML instead — component `config:` blocks are
passed straight to each adapter's constructor (`**cfg.config`).

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

Expected output: `modular-rag X.Y.Z` (e.g. `modular-rag 0.0.1`).

`cli/__init__.py`'s `version()` command prints `f"modular-rag {__version__}"` directly, reading
the same `importlib.metadata.version("modular-rag")`-backed value everything else in the codebase
does. Single source: `pyproject.toml`'s `[project].version`.

> At the current pre-alpha stage (`v0.0.x`), this command confirms the package is importable.
> End-to-end coverage already exists under `tests/e2e/`: a deterministic governed scenario runs in
> main CI and the real-LLM scenario runs in the scheduled/manual nightly workflow.
