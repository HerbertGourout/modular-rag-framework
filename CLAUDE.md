# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- Updated: 2026-05-22 — 9-block structure per official Claude Code recommendations -->
<!-- Revisit block 09 once VectorRetriever.retrieve() is finalized (V1 sprint in progress) -->
<!-- For personal preferences (Qdrant URL, API key, etc.): create CLAUDE.local.md (gitignored) -->

@.claude/.instructions.md
@.claude/.prompt.md

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

### Quick reference (for daily development)
```bash
# Install V1 deps + dev tools
pip install -e ".[v1,dev]"

# ⚡ QUICK CHECK (< 30s) — Use after any change
./scripts/check.sh quick        # Syntax + import order

# ✓ FULL CHECK (2-5 min) — Use before merge
./scripts/check.sh full         # Quick + unit + contracts

# 🔗 INTEGRATION (1-2 min) — With Qdrant
./scripts/check.sh integration

# 🚀 E2E TESTS (2-5 min) — Full pipeline
./scripts/check.sh e2e

# 📋 ALL CHECKS (~ 10 min) — Pre-release
./scripts/check.sh all
```

### Individual test scopes
```bash
# Unit tests (no external services)
pytest tests/unit/ -v

# Contract conformance tests (no external services)
pytest tests/contract/ -v

# Single test
pytest tests/unit/ingestion/chunkers/test_fixed.py::test_short_text_single_chunk -v

# Integration tests (requires Qdrant on localhost:6333)
pytest tests/integration/ -v -m integration

# E2E tests (requires Qdrant + LLM API key)
export MRAG_OPENAI_API_KEY=sk-...
pytest tests/e2e/ -v -m e2e
```

### CLI & API development
```bash
# REST API (development mode with hot-reload)
uvicorn modular_rag.api:create_app --factory --reload

# CLI ingestion
mrag ingest ./my_docs --manifest manifests/presets/local-hybrid-rag.yaml
mrag ask "What is hybrid retrieval?" --manifest manifests/presets/local-hybrid-rag.yaml

# End-to-end example
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
python examples/simple_qa/main.py ask "What is RAG?"
```

**→ Full command reference:** [docs/guides/validation.md](docs/guides/validation.md)  
**→ Validation strategies:** [.claude/settings.json (permissions)](`.claude/settings.json`)  
**→ Testing rules:** [.claude/rules/tests.md](.claude/rules/tests.md)

---

## 05 — Coding rules

<!-- These rules are the most critical ones. Path-specific rules live in .claude/rules/ -->

1. **Contracts first.** The `contracts/` Protocol must exist before any concrete implementation.
2. **No cross-domain imports.** Retrievers never import from `generation/`; guards never import from `ingestion/`. They share only `core/models/` types.
3. **Manifests are the source of truth.** Register the component in `orchestration/_default_factories.py`, then select it by name in YAML. Never wire it in Python elsewhere.
4. **Tests mirror `src/`.** `tests/unit/ingestion/chunkers/test_fixed.py` for `src/modular_rag/ingestion/chunkers/fixed.py`. Add a contract test in `tests/contract/` for every new Protocol implementation.
5. **Observability is mandatory.** Every retrieval, generation, and agent method must emit a `TraceStep` via `Trace.add_step()`.
6. **Extend, don't rewrite.** All core modules exist. Add to them rather than recreating.
7. **Lazy imports for heavy deps.** All optional libraries (qdrant-client, rank-bm25, sentence-transformers, openai, anthropic, fitz) must be imported inside the method that uses them, not at module level.
8. **State of the art first.** Before any *design* decision (fusion weights, chunking parameters, guard patterns, metric choices, architectural patterns), read the matching digest in `docs/research/` (DIGEST-retrieval, DIGEST-generation, DIGEST-chunking, DIGEST-evaluation, DIGEST-security, DIGEST-overviews, DIGEST-architecture — distilled from `.claude/research-papers/`) and cite the arXiv id backing the choice. A choice that contradicts the digest must be justified explicitly. Routine implementation (tests, fixes, wiring) does not require this.

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

## 09 — Roadmap: V1 → V5 with Strategic Features

<!-- Mise à jour : 2026-06-20 — Integrated 8 strategic features across V1-V5 -->

Strategic roadmap integrating **8 high-value features** that make this framework incontournable (irreplaceable).
See [ROADMAP.md](ROADMAP.md) for complete timeline and success criteria per version.

---

### V1 — Core RAG + Evaluation + Audit `[Q2 2026]`

**V1.0 — Hybrid Retrieval + Basic Security** ✅ (Current focus)
- ✅ Core RAG pipeline (ingestion → retrieval → generation)
- ✅ Hybrid retrieval (BM25 + vector + reranking)
- ✅ Security guards (prompt injection, PII redaction)
- ✅ Observability (TraceStep emissions throughout)
- ✅ ComponentRegistry + manifest wiring
- ✅ Unit, contract, integration, e2e tests
- ✅ `examples/simple_qa/` end-to-end

**V1.1 — Evaluation-as-Contract** `[NEW — 1 month after V1.0]`
- `contracts/evaluation.py`: MetricsProtocol for all components
- `eval/metrics/`: NDCG, MRR, semantic similarity, factuality, cost/query
- `eval/golden_sets/`: Domain-specific Q&A (finance, healthcare, manufacturing, default)
- `eval/regression_dashboard.py`: Auto-detect F1 drops, prevent merges
- **Key difference**: Every retriever/generator MUST implement metrics; tests contract conformance
- **Success**: F1 on golden set > 0.85, zero regressions

**V1.2 — Compliance Audit Trail** `[NEW — 2 months after V1.0]`
- `security/audit/`: Immutable append-only event store
- `security/audit/data_lineage_tracker.py`: Source → processing → response chain
- `security/redaction/`: Proof of what was redacted, how
- `security/compliance/`: Auto-generate GDPR/CCPA/HIPAA reports
- **Key difference**: GDPR audit report < 10 seconds; zero unredacted PII in logs
- **Success**: Audit trail immutable, data lineage traceable, compliance reports work

---

### V2 — Agentic + Policy Engine + Teams `[Q3 2026]`

**V2.0 — Multi-Agent Runtime + Policy-as-Code** `[UPDATED — P0 priority]`
- Multi-agent runtime: coordinator, planner, retriever, extractor, synthesizer, validator
- **NEW - Policy Engine** (moved from V4): `security/policies/`
  - Define policies in YAML (who can access what)
  - PolicyEngine evaluates queries vs policies before execution
  - Role-based access control (analyst vs director)
  - Data classification (public, internal, confidential, restricted)
  - Multi-tenant isolation (tenant A cannot see tenant B)
- **Key difference vs V1**: Governance is now proactive (prevent bad queries) not just reactive
- **Success**: Policies enforced, multi-tenant isolation works, violations logged

**V2.1 — Collaborative Multi-Agent Teams** `[NEW — 3 months after V2.0]`
- `agents/domain_specialist/`: Expert agents for specific domains
- `agents/fact_checker/`: Validates answers against retrieved docs
- `agents/collaboration/`: Consensus scoring, conflict resolution
- `orchestration/team_coordinator.py`: Orchestrate which agents run, in what order
- **Example workflow**: HR question → HR specialist + Legal + Finance agents → synthesis
- **Key difference**: Transparency (know why each agent was involved), accountability
- **Success**: Team queries executable, consensus > 85%, full reasoning trace

---

### V3 — Graph Memory + Cost Optimization + Fine-Tuning `[Q4 2026]`

**V3.0 — GraphRAG + Knowledge Graphs**
- Knowledge graph construction from corpus
- GraphRAG retrieval (sub-graph selection, multi-hop reasoning)
- Community detection + hierarchical summaries
- Neo4j adapter for `adapters/graphstores/`
- EvoRAG: edge reinforcement from user feedback
- **Success**: 3-hop reasoning works, F1 > 0.80 on graph queries

**V3.1 — Cost Optimization Engine** `[NEW — 2 months after V3.0]`
- `orchestration/cost_optimizer/`: Query classifier (factual vs reasoning)
- Smart routing: BM25 → GPT-3.5 if factual, GPT-4 only if reasoning-heavy
- Multi-model support: Mix GPT-4, GPT-3.5, local LLMs
- `orchestration/query_cache.py`: Hash-based caching, return cached if > 95% similar
- `eval/cost_reporting/`: Dashboard (cost/query, per user, per month)
- **Example impact**: 10k queries/month → $300 → $41.50 (86% savings)
- **Success**: 70% queries routed to cheap path, cost reduction > 50%

**V3.2 — Continuous Fine-Tuning Loop** `[NEW — 3 months after V3.0]`
- `eval/feedback_collection/`: Thumbs up/down, user corrections
- `eval/drift_detection.py`: Monitor F1 vs baseline
- `orchestration/auto_fine_tuning/`: Auto-retrain on corrections
- `orchestration/model_versioning/`: Track versions, rollback if regress
- **Example workflow**: User corrects 50 queries → auto-fine-tune embedder → F1 improves 2-5%
- **Key difference**: RAG that learns autonomously; never manual retraining
- **Success**: Feedback > 80%, drift detected, F1 improves monthly

---

### V4 — Multi-Language + Governance `[Q1 2027]`

**V4.0 — Multi-Tenant Policies + Multi-Environment**
- Policy-as-code enhancements (OPA integration)
- Multi-environment manifests (dev/staging/prod)
- Human-in-the-loop: review queue for risky answers
- Risk profiles per pipeline
- **Success**: Prod policies enforced, escalation queue works

**V4.1 — Multi-Language + Cultural Reasoning** `[NEW — 4 months after V4.0]`
- `adapters/nlp/`: Language-specific tokenizers (Arabic, Chinese, French, German, etc.)
- `ingestion/chunkers/multilingual_chunker.py`: Respect sentence boundaries per language
- `adapters/embeddings/multilingual_embeddings.py`: mxbai-embed-large (50+ languages)
- `generation/`: Language-aware generation (preserve language, no forced translation)
- `security/cultural_policies/`: Regulatory routing (GDPR EU, CCPA US, CNIL France)
- **Key difference**: Global-by-default (not English-first); cultural context in answers
- **Success**: 20+ languages native, F1 in non-English > 0.80, regulatory routing works

---

### V5 — Multimodal Intelligence `[Q2 2027]`

**V5.0 — Images, Audio, Video, Tables + VLMs**
- Multimodal parsers: image, table, audio transcription (Whisper), video segmentation
- Multi-vector Qdrant index (text + image + table)
- MG²-RAG: multi-granularity cross-modal graph
- Modality-specialized agents: text, vision, table, video agents
- VLM generation (Claude vision, GPT-4V)
- Enriched citations: image references, timecodes
- **Success**: Multimodal QA on PDFs with charts, VLM integration works

---

### Adapter Stubs (V2-V5 Scope)
| Stub | Scope | Implementation Timeline | Notes |
|------|-------|--------------------------|-------|
| `adapters/llms/` | V2 | Multi-model: GPT-4, GPT-3.5, local | Cost optimizer requires this |
| `adapters/auth/` | V4 | OAuth, API key, tenant isolation | Policies (V2) → Auth (V4) |
| `adapters/graphstores/` | V3 | Neo4j, ArangoDB | GraphRAG requires this |
| `adapters/search/` | V2-V3 | Elasticsearch, Algolia | Multi-provider search |

**Rule**: Do NOT add implementations to these directories before their version. Leave `.gitkeep` files. They are reserved namespaces.

---

### Test Stubs Status
| Path | Status | Version | Notes |
|------|--------|---------|-------|
| `tests/integration/` | ✅ Exists | V1 | Run: `pytest tests/integration -m integration` |
| `tests/e2e/` | ✅ Exists | V1 | Run: `pytest tests/e2e -m e2e` (full pipeline) |
| `tests/benchmark/` | 🚫 Empty | V3 | Performance baselines added in V3 |
| `tests/policy/` | 🚫 Empty | V2 | Policy conformance tests in V2 |
| `tests/multimodal/` | 🚫 Empty | V5 | Multimodal tests in V5 |

**Rule**: Create test modules in the version that introduces the feature.

---

### Manifest Stubs Status
| Path | Purpose | Target Version | Status |
|------|---------|-----------------|--------|
| `manifests/dev/` | Development configs | V2 | Populated in V2 with policy variants |
| `manifests/staging/` | Staging configs | V4 | Populated in V4 with prod-like policies |
| `manifests/production/` | Production configs | V4 | Populated in V4 with full governance |
| `manifests/policies/` | Policy YAML | V2 | Created in V2 with examples |

**Rule**: Don't populate until version target. Use `manifests/presets/local-hybrid-rag.yaml` as reference in V1.

---

### Implementation Order (Do NOT Skip Versions)

**CRITICAL**: Versions are sequential. Do not implement V3 features in V1.

```
V1 — V1.0 → V1.1 → V1.2 (complete V1 before V2)
V2 — V2.0 → V2.1 (complete V2 before V3)
V3 — V3.0 → V3.1 → V3.2 (complete V3 before V4)
V4 — V4.0 → V4.1 (complete V4 before V5)
V5 — V5.0
```

Why sequences matter:
- V1.1 (Evaluation) depends on V1.0 (core components to evaluate)
- V1.2 (Audit) depends on V1.0 + V1.1 (what to audit)
- V2.0 (Agents) depends on V1.x (they use V1 components)
- V2.1 (Teams) depends on V2.0 (requires agent runtime)
- V3.1 (Cost Opt) depends on V3.0 (optimize what's expensive)
- V4.1 (Multi-Lang) depends on V4.0 (governance framework)

---

### Wiring Notes (V1 Internals)
- `VectorRetriever._embedder` and `VectorRetriever._store` are injected by `registry.wire()` post-wiring.
- `HybridRetriever` uses `k` (retrieval count) and `reranker_k` from manifest config.
- All components wired via `orchestration/registry.py` — never direct Python instantiation.

---

### Questions?

**"When do I implement Policy Engine?"**
→ V2.0 (not V1). It requires agent orchestration context. See [ADR-0003](docs/adr/0003-security-and-governance.md).

**"Do I need multi-language in V1?"**
→ No. V1 is English. V4.1 adds 20+ languages. For now, use mxbai-embed-large (which handles multiple languages by default, but don't expect perfect quality in V1).

**"Can I do fine-tuning in V2?"**
→ Not recommended. V3.2 is the target. V2-V3 focus on reasoning + retrieval quality first.

**"What if client asks for V5 features in V1?"**
→ Explain the strategy: "V1 is proven RAG. V2 adds governance and agents. V3 adds intelligence. V4 adds compliance. V5 adds multimodal." Each version compounds on the previous.

**"What about benchmarks?"**
→ V3+. V1-V2 use golden sets (eval). V3 adds performance benchmarks and tracking.

---

### Key Differentiators (Why This Roadmap is Incontournable)

| Capability | LangChain | Haystack | **This Framework** |
|---|---|---|---|
| Evaluation | External | Built-in | ✅ **Contract-enforced (V1.1)** |
| Audit Trail | Manual logs | Limited | ✅ **GDPR-ready (V1.2)** |
| Policies | None | Limited | ✅ **Policy-as-Code (V2.0)** |
| Multi-Agent | Bolted-on | Limited | ✅ **Team collaboration (V2.1)** |
| Cost Optimization | None | None | ✅ **Auto-routing (V3.1)** |
| Fine-Tuning | None | None | ✅ **Continuous learning (V3.2)** |
| Graph Memory | External | External | ✅ **Native GraphRAG (V3.0)** |
| Multi-Language | English-first | Limited | ✅ **20+ languages (V4.1)** |
| Multimodal | Partial | Partial | ✅ **Full VLM support (V5.0)** |
