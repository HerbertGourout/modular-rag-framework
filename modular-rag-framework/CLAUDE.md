# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state — read this first

This repository is a **pre-alpha scaffold** with a full V1→V5 implementation skeleton as of 2026-05-21.

### What exists and works

- **All `.py` files under `src/modular_rag/`** are fully implemented (contracts, core models, ingestion, retrieval, generation, security, eval, agents, memory, orchestration, CLI, API, observability).
- **All 5 YAML manifests** under `manifests/presets/` are populated with real configuration.
- **All 3 ADRs** under `docs/adr/` are written.
- **All architecture docs** under `docs/architecture/` are filled.
- **All guides** under `docs/guides/` are written.
- **`pyproject.toml`** — complete with all dependency groups (`v1`, `v3`, `v4`, `v5`, `dev`, `all`) and entry point `mrag`.
- **`LICENSE`** — Apache 2.0 full text.
- **`examples/simple_qa/`** — `main.py` + `README.md` + sample docs.
- **Adapter implementations**: `adapters/embeddings/openai_embedder.py`, `adapters/embeddings/hf_embedder.py`, `adapters/vectorstores/qdrant_store.py`.
- **Unit tests**: `tests/unit/core/`, `tests/unit/ingestion/chunkers/`, `tests/unit/security/`, `tests/unit/retrieval/`, `tests/unit/eval/`, `tests/unit/memory/`.
- **Contract tests**: `tests/contract/test_chunker_conformance.py`, `tests/contract/test_retrieval_conformance.py`, `tests/contract/test_security_conformance.py`, `tests/contract/test_eval_conformance.py`.

### What still needs work (to run end-to-end)

- **`VectorRetriever.retrieve()`** — raises `NotImplementedError`; needs embedder wired to `QdrantStore.retrieve_by_vector()`.
- **`pip install -e ".[v1]"` and `pytest tests/unit`** — should work once dependencies are installed, but has not been tested in CI yet.
- **`examples/simple_qa/` end-to-end** — requires Qdrant running locally + OpenAI API key.
- **`adapters/auth/`, `adapters/graphstores/`, `adapters/llms/`, `adapters/search/`** — still have only `.gitkeep` placeholders.
- **`tests/integration/`, `tests/e2e/`, `tests/benchmark/`** — no test files yet.
- **`docs/guides/_index.md`, `docs/api/_index.md`, `docs/_index.md`** — index stubs, not filled.

**Implication for Claude**: all core modules now exist and are importable. When adding new code, extend existing modules rather than rewriting them. Verify imports resolve before assuming they work.

## Architectural intent

The framework is being built around three pillars (see `README.md` → *Vision*):

1. **Declarative orchestration** — pipelines are described in YAML manifests under `manifests/`, not in Python code.
2. **Composable retrieval & generation** — every capability has a contract under `src/modular_rag/contracts/`, and implementations sit elsewhere.
3. **Agentic, verifiable reasoning** — multiple specialized agents (planner, retriever, synthesizer, validator, coordinator) replace the monolithic LLM call.

### Layered module model

The `src/modular_rag/` tree encodes a strict hexagonal-style separation. **Code must respect these layers** when implemented:

| Layer | Path | Role |
|---|---|---|
| **Contracts** (interfaces) | `contracts/` | Protocols / ABCs. Everything else depends on these, never the other way around. |
| **Core models** (data) | `core/models/` | Pydantic-style domain entities: `document`, `chunk`, `query`, `retrieved`, `answer`, `trace`, `policy`, `metrics`. Shared by all layers. |
| **Adapters** (integrations) | `adapters/` | External-system bindings: `llms/`, `embeddings/`, `vectorstores/`, `graphstores/`, `search/`, `auth/`. Implements `contracts/`. |
| **Orchestration** | `orchestration/` | `engine`, `router`, `flow_compiler`, `state_machine`, `registry`. Compiles manifests into runnable flows. |
| **App** | `app/` | Process-level wiring: `bootstrap`, `container` (DI), `settings`, `lifecycle`. |
| **Domain modules** | `ingestion/`, `retrieval/`, `generation/`, `agents/`, `security/`, `memory/`, `eval/`, `observability/` | Concrete implementations of `contracts/`, organized by domain. |
| **Edges** | `cli/`, `api/` | User-facing entry points. |

**Dependency rule**: `domain modules` → `contracts` + `core/models`. They must **not** import from each other directly — they communicate through contracts wired by the `container`/`registry`.

### Five-version roadmap

The directory layout already anticipates V1 → V5. When implementing, respect which version a feature belongs to:

| Version | Theme | Modules involved |
|---|---|---|
| V1 | Core RAG | `ingestion/`, `retrieval/` (vector + BM25 + fusion), `generation/`, basic `security/`, `eval/`, `observability/`, `manifests/presets/local-hybrid-rag.yaml`, `manifests/presets/secure-enterprise-rag.yaml` |
| V2 | Agentic + Security | `agents/` (planner/coordinator/extractor/synthesizer/validator), `orchestration/router`, advanced `security/policies` and `security/detectors`, `manifests/presets/agentic-rag.yaml` |
| V3 | Graph Memory | `memory/graph/`, `memory/versioning/`, retrieval planners for multi-hop, `manifests/presets/graph-memory-rag.yaml` |
| V4 | Governance | `security/policies/`, `manifests/{dev,staging,production}/`, audit hooks in `observability/`, policy-as-code in `contracts/security.py` |
| V5 | Multimodal | New modules to create (`multimodal/`, `vision/`, `tables/`, `audio/`) + multimodal agents, `manifests/presets/multimodal-rag.yaml` |

Do not implement V3+ capabilities until V1 has a working `examples/simple_qa/` end-to-end.

## Conventions to apply when implementing

These rules are derived from the architecture review and the cahier technique. They are **not yet enforced by code** because no code exists — apply them by hand.

1. **Contracts first.** Before adding any concrete class under `ingestion/`, `retrieval/`, `generation/`, etc., the matching protocol in `contracts/` must already exist and be referenced.
2. **No cross-domain imports.** A retriever must not import from `generation/`. They meet only through `core/models/` types and `contracts/` protocols.
3. **Manifests are the source of truth.** A new component is wired by adding it to the registry and selectable by name in a YAML manifest — not by Python wiring inside another module.
4. **Tests mirror `src/`.** When writing the first tests, create `tests/unit/<same_path_as_src>/test_<name>.py`. There is also a dedicated `tests/contract/` folder for tests that verify a concrete implementation satisfies the protocol it claims to implement.
5. **ADR before structural changes.** Anything that affects the layering (new top-level module, new edge between layers, change to a contract) requires a new ADR under `docs/adr/`. The first three ADR filenames are reserved (`0001-modular-architecture`, `0002-contracts-and-plugins`, `0003-security-and-governance`).
6. **Observability is mandatory, not optional.** Any new contract method that does retrieval, generation, or agent decisions must emit a `Trace` (see `core/models/trace.py`). The framework's value proposition depends on this.
7. **Safety vs. Security are distinct.** `security/` currently mixes both. When implementing, treat *safety* (prompt injection, data poisoning, output toxicity) as a sub-concern separate from *security* (RBAC, ACL, tenant isolation). The review (`docs/reviews/2026-05-20-initial-review.md` §3.8) flagged this for a future split.

## Commands

```powershell
# Install (all V1 deps + dev tools)
pip install -e ".[v1,dev]"

# Run unit tests (no external services required)
pytest tests/unit

# Run contract conformance tests (no external services required)
pytest tests/contract

# Run integration tests (requires Qdrant on localhost:6333)
pytest tests/integration

# Run a single test
pytest tests/unit/ingestion/chunkers/test_fixed.py::test_short_text_single_chunk

# Start the REST API
uvicorn modular_rag.api:create_app --factory --reload

# CLI — ingest documents
mrag ingest ./my_docs --manifest manifests/presets/local-hybrid-rag.yaml

# CLI — ask a question
mrag ask "What is hybrid retrieval?" --manifest manifests/presets/local-hybrid-rag.yaml

# Run the simple_qa example end-to-end
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
python examples/simple_qa/main.py ask "What is RAG?"
```

## Repository hosting

The remote is on a private GitLab instance (`pscode.lioncloud.net`, Publicis). The README labels the project "open-source" but it currently has no public mirror. **Do not push assumptions about GitHub workflows or public visibility** — CI templates and issue templates live under `.gitlab/`, not `.github/`.

## Reference documents

- `README.md` — project pitch, target API, V1→V5 roadmap. Already updated to reflect pre-alpha status.
- `docs/reviews/2026-05-20-initial-review.md` — full structural and editorial review, with P0/P1/P2 action items and progress checkboxes. **Read this before doing any large change** — it captures decisions (e.g. Apache 2.0 license choice) and known issues.
- `ROADMAP.md` — V1→V5 checkboxes with milestone criteria.
- `CHANGELOG.md` — [Unreleased] section with all current additions.
- `docs/architecture/overview.md` — full V1→V5 technical specification.
- `docs/architecture/roadmap-mermaid.md` — Mermaid diagrams for all versions.
- `docs/guides/getting-started.md` — first-run walkthrough.
- `docs/guides/plugin-development.md` — how to add a new component.
- `docs/api/rest.md` — REST API endpoint reference.
- `examples/simple_qa/` — runnable end-to-end example with sample docs.
