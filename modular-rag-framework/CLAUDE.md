# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- Mis à jour : 2026-05-22 — structure en 9 blocs selon recommandations officielles Claude Code -->
<!-- Revoir le bloc 09 quand VectorRetriever.retrieve() sera fixé (V1 sprint en cours) -->
<!-- Pour ajouter des préférences personnelles (URL Qdrant, clé API, etc.) : créer CLAUDE.local.md (gitignored) -->

---

## 01 — Project purpose

Production-grade modular RAG + agentic orchestration framework for Publicis enterprise use cases. Five-version progression: V1 (Core RAG) → V2 (Agentic) → V3 (Graph Memory) → V4 (Governance) → V5 (Multimodal).

**Non-negotiable priority**: do not implement V3+ features until `examples/simple_qa/` runs end-to-end. V1 is the current target.

---

## 02 — Architecture rules

Strict hexagonal layering. Dependencies flow in one direction only:

```
cli/ + api/  →  app/  →  orchestration/  →  contracts/ + core/
                                              ↑
                         domain modules  ────┘
                         (ingestion, retrieval, generation,
                          security, agents, memory, eval)
                                              ↑
                         adapters/  ──────────┘
```

**Hard rules:**
- `core/` imports nothing from this project.
- `contracts/` imports only `core/`.
- Domain modules import only `contracts/` + `core/models/`. **Never from each other.**
- `adapters/` imports `contracts/` + `core/` + external libs. Never from domain modules.
- A new component is wired only through `orchestration/registry.py` + a YAML manifest. No Python-level wiring inside other modules.

---

## 03 — Project structure

@.claude/project-structure.md

---

## 04 — Development commands

```powershell
# Install V1 deps + dev tools
pip install -e ".[v1,dev]"

# Unit tests (no external services)
pytest tests/unit

# Contract conformance tests (no external services)
pytest tests/contract

# Single test
pytest tests/unit/ingestion/chunkers/test_fixed.py::test_short_text_single_chunk

# Integration tests (Qdrant required on localhost:6333)
pytest tests/integration

# REST API
uvicorn modular_rag.api:create_app --factory --reload

# CLI
mrag ingest ./my_docs --manifest manifests/presets/local-hybrid-rag.yaml
mrag ask "What is hybrid retrieval?" --manifest manifests/presets/local-hybrid-rag.yaml

# End-to-end example
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
python examples/simple_qa/main.py ask "What is RAG?"
```

---

## 05 — Coding rules

<!-- Ces règles sont les plus critiques. Les règles path-spécifiques vivent dans .claude/rules/ -->

1. **Contracts first.** The `contracts/` Protocol must exist before any concrete implementation.
2. **No cross-domain imports.** Retrievers never import from `generation/`; guards never import from `ingestion/`. They share only `core/models/` types.
3. **Manifests are the source of truth.** Register the component in `orchestration/_default_factories.py`, then select it by name in YAML. Never wire it in Python elsewhere.
4. **Tests mirror `src/`.** `tests/unit/ingestion/chunkers/test_fixed.py` for `src/modular_rag/ingestion/chunkers/fixed.py`. Add a contract test in `tests/contract/` for every new Protocol implementation.
5. **Observability is mandatory.** Every retrieval, generation, and agent method must emit a `TraceStep` via `Trace.add_step()`.
6. **Extend, don't rewrite.** All core modules exist. Add to them rather than recreating.
7. **Lazy imports for heavy deps.** All optional libraries (qdrant-client, rank-bm25, sentence-transformers, openai, anthropic, fitz) must be imported inside the method that uses them, not at module level.

---

## 06 — Testing and validation

After any change, run the appropriate scope:

| Scope | Command | Requires |
|---|---|---|
| Core logic | `pytest tests/unit` | nothing |
| Protocol conformance | `pytest tests/contract` | nothing |
| Vector store | `pytest tests/integration` | Qdrant on :6333 |
| Full pipeline | `pytest tests/e2e` | Qdrant + LLM API key |

A change to a contract (`contracts/`) requires updating the matching `tests/contract/test_*_conformance.py`. A new domain implementation requires a unit test in `tests/unit/<same_path>/`.

---

## 07 — Security rules

- **Never import** a domain module from another domain module — this is the most common violation to watch for.
- **Safety ≠ Security.** Safety (prompt injection, PII, toxicity) lives in `security/filters/` and `security/redaction/`. Security (RBAC, tenant isolation, policy enforcement) lives in `security/policies/`. Do not mix them.
- **ADR before structural changes.** Any new top-level module, new layer boundary, or contract modification requires a new ADR under `docs/adr/`. ADRs 0001–0003 are reserved.
- **No V3+ code until V1 is end-to-end.** Graph, governance, and multimodal features must wait.

---

## 08 — Git and PR workflow

- Remote: **private GitLab** at `pscode.lioncloud.net` (Publicis). No public GitHub mirror.
- CI templates and issue templates are under **`.gitlab/`**, not `.github/`.
- Do not reference GitHub Actions, GitHub Issues, or GitHub PRs — use GitLab MR terminology.
- Branch from `main`. One feature per branch. MR checklist is in `CONTRIBUTING.md`.

---

## 09 — Compact instructions (known stubs)

<!-- Mettre à jour ce bloc après chaque sprint V1 -->

Current V1 gaps to be aware of before touching retrieval or wiring:

- `retrieval/retrievers/vector.py` → `VectorRetriever.retrieve()` raises `NotImplementedError`. Fix: embed query with `self.embedder`, call `self.store.retrieve_by_vector()`.
- `adapters/llms/`, `adapters/auth/`, `adapters/graphstores/`, `adapters/search/` → `.gitkeep` only.
- `tests/integration/`, `tests/e2e/`, `tests/benchmark/` → no test files yet.
- `manifests/dev/`, `manifests/staging/`, `manifests/production/` → empty stubs (V4 scope).
