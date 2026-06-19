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

## 09 — Known Stubs & V2+ Scope

<!-- Mise à jour : 2026-06-19 — Phase 3 clarification complète -->

V1 is end-to-end functional. Stubs below are **V2+ scope** and must NOT be implemented in V1. See [.claude/.instructions.md section 7](.claude/.instructions.md#7-version-scope-v1-vs-v2) and [.claude/rules/agentic_workflows.md](.claude/rules/agentic_workflows.md) for V2+ patterns.

### Adapter Stubs (V2-V5 Scope)
| Stub | Scope | Why Deferred | Implementation Notes |
|------|-------|-------------|----------------------|
| `adapters/llms/` | V2 | Requires LLM agent orchestration | Will implement OpenAI, Anthropic, local LLM bindings in V2 |
| `adapters/auth/` | V4 | Requires policy engine + RBAC | Will implement OAuth, API key, tenant isolation in V4 |
| `adapters/graphstores/` | V3 | Requires knowledge graph module | Will implement Neo4j, ArangoDB bindings in V3 |
| `adapters/search/` | V2-V3 | Requires semantic search + multi-provider | Will implement Elasticsearch, Algolia bindings in V2-V3 |

**Rule**: Do NOT add implementations to these directories. Leave `.gitkeep` files in place. They serve as reserved namespace markers.

### Test Stubs
| Path | Status | Requirements | Action |
|------|--------|--------------|--------|
| `tests/integration/` | ✅ Exists | Qdrant on localhost:6333 | Run: `pytest tests/integration -m integration` |
| `tests/e2e/` | ✅ Exists | Qdrant + `$env:MRAG_OPENAI_API_KEY` | Run: `pytest tests/e2e -m e2e` (full pipeline) |
| `tests/benchmark/` | 🚫 Empty | Requires performance baselines | V3+ scope: defer until after V1 completion |

### Manifest Stubs (V4 Scope)
| Path | Purpose | Status | Notes |
|------|---------|--------|-------|
| `manifests/dev/` | Development pipeline configs | 🚫 Empty | Will populate with local-hybrid-rag.yaml variants |
| `manifests/staging/` | Staging pipeline configs | 🚫 Empty | Will populate with production-like configs |
| `manifests/production/` | Production pipeline configs | 🚫 Empty | V4 scope: requires governance + audit trails |

**Rule**: `local-hybrid-rag.yaml` in `manifests/presets/` is the reference. Do NOT duplicate it to dev/staging/production yet.

### V1 Completed ✅
- ✅ Core RAG pipeline (ingestion → retrieval → generation)
- ✅ Hybrid retrieval (BM25 + vector + reranking)
- ✅ Security guards (prompt injection, PII redaction, basic policies)
- ✅ Observability (TraceStep emissions throughout pipeline)
- ✅ ComponentRegistry + manifest wiring pattern
- ✅ Unit, contract, integration, e2e test scopes
- ✅ `examples/simple_qa/` end-to-end working

### V2 Preview (Do NOT Implement in V1)
- Agent orchestration (Coordinator, Planner, Retriever, Generator agents)
- Multi-turn conversation support
- Tool use patterns
- Advanced query routing (decision trees)
- See [.claude/rules/agents.md](.claude/rules/agents.md) and [.claude/rules/agentic_workflows.md](.claude/rules/agentic_workflows.md) for V2+ patterns.

### V3-V5 Future (Completely Out of Scope in V1)
- **V3**: Knowledge graph memory, versioning, EvoRAG
- **V4**: Governance, audit, compliance, RBAC, tenant isolation
- **V5**: Multimodal (images, video, audio)

### Wiring Notes (V1 Internals)
- `VectorRetriever._embedder` and `VectorRetriever._store` are injected by `registry.wire()` post-wiring — do not pass them via manifest config.
- `HybridRetriever` passes `k` (retrieval count) and `reranker_k` (reranking count) from manifest config. Use `k` at query time, `reranker_k` for engine-level reranking.
- All components are wired via `orchestration/registry.py` — never instantiate directly in Python code. Use manifest YAML instead.

### When to Revisit This
- After `examples/simple_qa/` runs end-to-end ✅ (DONE)
- After `pytest tests/unit tests/contract` passes 100% (VERIFY)
- After stakeholder sign-off on V1 scope (CHECK)
- **Then** start V2 planning and implementation
- **Then** populate adapters/llms/ and adapters/search/
- **Then** implement agent orchestration patterns

### Questions?
- "Can I implement X in V2 scope?" → Check [ADR-0002](.adr/0002-contracts-and-plugins.md) and [.claude/rules/agentic_workflows.md](.claude/rules/agentic_workflows.md) for patterns.
- "Why not implement agents now?" → V2 agents require extensive refactoring of orchestration. Defer until V1 is locked in.
- "What's in adapters/llms/?" → Nothing yet. LLM adapters come with V2 agent support. See `adapters/embeddings/` for current binding pattern.
