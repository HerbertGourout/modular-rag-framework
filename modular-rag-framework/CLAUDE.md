# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state — read this first

This repository is a **pre-alpha scaffold**. As of the last initial review (`docs/reviews/2026-05-20-initial-review.md`):

- All `.py` files under `src/modular_rag/` are **0 lines** — interfaces are not yet implemented.
- All YAML manifests under `manifests/presets/` are **0 lines** — only the filenames exist.
- All docs under `docs/architecture/`, `docs/adr/`, `docs/guides/`, `docs/api/` are **0 lines**.
- `pyproject.toml` is empty — `pip install -e .` will not work yet.
- The only file with real content is `README.md`, which describes the **target API for v0.1**, not what runs today.

**Implication for Claude**: do not assume any module, function, or contract already exists. When asked to implement something, treat the directory tree as the architecture contract, but write the code from scratch. Do not invent imports from modules that have no content.

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

The build/test/run commands described in the README are **target commands** for v0.1 — they do not work yet (empty `pyproject.toml`, no entry points). When implementation starts, the intended commands are:

```powershell
# Install (target — not functional yet)
pip install -e .

# Run tests (target — pytest is the intended runner per docs/architecture)
pytest tests/unit
pytest tests/integration
pytest tests/contract            # contract conformance tests
pytest tests/e2e

# Single test (target convention)
pytest tests/unit/<path>/test_<name>.py::test_<case>

# Load a pipeline from a manifest (target API)
python -c "from modular_rag.app.bootstrap import load_pipeline; p = load_pipeline('manifests/presets/local-hybrid-rag.yaml'); print(p.answer('hello'))"
```

**Before claiming any of these work**, verify by actually running them. Until `pyproject.toml` is populated and at least one contract + one implementation exist, none of them will.

## Repository hosting

The remote is on a private GitLab instance (`pscode.lioncloud.net`, Publicis). The README labels the project "open-source" but it currently has no public mirror. **Do not push assumptions about GitHub workflows or public visibility** — CI templates and issue templates live under `.gitlab/`, not `.github/`.

## Reference documents

- `README.md` — project pitch, target API, V1→V5 roadmap. Already updated to reflect pre-alpha status.
- `docs/reviews/2026-05-20-initial-review.md` — full structural and editorial review, with P0/P1/P2 action items and progress checkboxes. **Read this before doing any large change** — it captures decisions (e.g. Apache 2.0 license choice) and known issues.
- `ROADMAP.md`, `CHANGELOG.md` — currently empty, to be filled when implementation starts.
- The full technical specification (cahier technique) belongs in `docs/architecture/overview.md` — currently empty. If asked to "explain the architecture", warn the user that this file is empty and refer to the README + this CLAUDE.md instead.
