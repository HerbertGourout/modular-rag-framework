# Modular RAG Framework — Complete Overview & Onboarding

**For**: All team members (developers, architects, product managers, stakeholders)
**Purpose**: Understand what this framework is, why it exists, what it does now, and what's coming
**Rewritten**: 2026-08-06 (documentation audit, `docs/documentation-audit-2026-08.md`)
**Status**: V1 complete; a full 18-lot engine-agnostic control-plane refactoring programme
(2026-08-03 → 2026-08-06) has also shipped — see [docs/refactoring/README.md](../refactoring/README.md)

> **What changed in this rewrite**: the previous version (dated June 2026) described a native
> V2 "multi-agent runtime (coordinator, planner, retriever, synthesizer, validator)" and native
> V3 GraphRAG as forward roadmap items, with code sketches using classes
> (`RetrieverProtocol`, `GPTGenerator`, `PiiFilter`...) that never existed in this codebase.
> [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) (accepted 2026-08-04) redrew
> that plan: this framework owns governance, audit, evaluation, tenant isolation, and
> portability natively, and **delegates** generic multi-agent orchestration and GraphRAG
> traversal to a selected external engine (LangGraph, [ADR-0006](../adr/0006-external-engine-selection.md))
> via a vendor-neutral `DocumentEngine` port. This version reflects that split throughout.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Why This Framework Exists](#why-this-framework-exists)
3. [What Is It?](#what-is-it)
4. [Architecture at a Glance](#architecture-at-a-glance)
5. [Current Status](#current-status)
6. [Owned vs. Delegated: V2-V5](#owned-vs-delegated-v2-v5)
7. [Quick Start by Role](#quick-start-by-role)
8. [Key Differentiators](#key-differentiators)
9. [Business Impact](#business-impact)
10. [Get Started](#get-started)
11. [FAQ](#faq)

---

## Executive Summary

**Modular RAG Framework** is a production-grade, reusable foundation for building enterprise
Retrieval-Augmented Generation (RAG) systems — an engine-neutral **control plane**: governance,
audit, evaluation, tenant isolation, and portability owned natively, wrapped around whichever
execution engine (native or a selected external one) actually runs a request.

### Key facts (verified against current code, not aspirational)

- **V1 (Core RAG)**: complete — ingestion, hybrid retrieval (vector + BM25 + RRF), reranking,
  generation, security guards, tenant isolation, audit trail, document lifecycle, quality gates,
  API/CLI hardening, dependency/licence gates, an immutable container build.
- **Engine abstraction**: complete — `contracts/engine.py`'s `DocumentEngine` port has two real
  implementations (`NativeEngineAdapter`, wrapping the native pipeline; `LangGraphEngineAdapter`,
  running the same governed components through a real LangGraph `StateGraph`), selectable per
  manifest with no governance rewrite.
- **V2.0's Policy Engine**: real and shipped (`security/policies/policy_engine.py`,
  `TenantIsolationPolicy`) — not deferred, per ADR-0005 §5.1.
- **V2.1 (multi-agent teams), V3.0 (GraphRAG), V3.2 (fine-tuning execution), V5.0 (multimodal
  execution)**: delegated to the selected external engine, not native builds. A prior native
  prototype for the agent roles existed and was removed (zero test coverage, zero consumers) in
  the same refactoring programme that shipped the delegation port.

---

## Why This Framework Exists

### The Problem

Most RAG projects start from scratch:
- ❌ Reinventing chunking strategy (weeks wasted)
- ❌ Building security guards manually (compliance risk)
- ❌ No evaluation framework (ship low-quality systems)
- ❌ No audit trail (regulatory violations)
- ❌ Tightly coupled to one LLM (locked to vendor)
- ❌ No observability (black box in production)

### The Solution

A reusable, governed, observable control plane that:
- ✅ Orchestrates RAG components via YAML manifests (no Python wiring)
- ✅ Enforces clean architecture (hexagonal layering, checked in CI)
- ✅ Includes security by design (guards, redaction, fail-closed tenant isolation)
- ✅ Provides observability from day one (tracing, audit events)
- ✅ Evaluation-as-contract (quality gates, versioned metrics)
- ✅ Works with any LLM, any vector store, any chunker — and, since Lot 15, either the native
  engine or a selected external one (LangGraph), behind the same port

### Business Impact

| Dimension | Impact |
|-----------|--------|
| **Delivery** | Faster per-project setup — security, audit, and evaluation are already built, not rebuilt each time |
| **IP** | Reusable across projects (Publicis keeps it) |
| **Differentiation** | An owned engine-neutral control plane, not a from-scratch build per client |
| **Regulation** | GDPR/CCPA-relevant audit trail and tenant isolation built-in (see caveats in §5) |
| **Knowledge** | Compounds across projects (adapters, manifests, policies) |

---

## What Is It?

**Modular RAG Framework** = **Engine-neutral orchestration port** + **Component protocols** +
**Security/governance policies** + **Observability** + **Audit**.

It's **not**:
- ❌ A competitor to LangChain/LlamaIndex on breadth of native agent/graph tooling — since
  ADR-0005 it deliberately delegates that territory rather than rebuilding it
- ❌ A SaaS (self-hosted)
- ❌ A monolithic RAG implementation

It **is**:
- ✅ A metaframework for composing RAG components behind stable contracts
- ✅ Protocol-driven (Pydantic models, `typing.Protocol` interfaces)
- ✅ Manifest-based (YAML configuration, `ComponentRegistry.wire()`)
- ✅ Modular (swap any component without touching others)
- ✅ Security-first (see [architecture/security.md](../architecture/security.md))
- ✅ Observable (`TraceStep`, `AuditEvent`)
- ✅ Engine-portable (native or LangGraph today, same governance either way)

### Core concepts

**1. Hexagonal layering** — `core/` and `contracts/` at the bottom, domain modules
(`ingestion/`, `retrieval/`, `generation/`, `security/`, `eval/`, `memory/`) depend only on
those two, `adapters/` implements the contracts against real libraries, `orchestration/`/`app/`
wire everything, `cli/`/`api/` are the entry points. Enforced by `scripts/check_layering.py`,
not just documented. See [architecture/module-model.md](../architecture/module-model.md).

**2. Protocol-first design** — every component implements a real Protocol before an
implementation exists, e.g. `contracts/retrieval.py`'s `Retriever` → `VectorRetriever`,
`BM25Retriever`, `HybridRetriever`; `contracts/generation.py`'s `Generator` →
`OpenAIGenerator`, `AnthropicGenerator`.

**3. Manifest-driven wiring** — instead of Python instantiation, a manifest selects components
by name:

```yaml
# manifests/presets/local-hybrid-rag.yaml (the one preset that actually wires end to end —
# see manifests/README.md for why the other four don't yet)
retriever:
  type: hybrid
  config:
    k: 20
generator:
  type: openai
  config:
    model: gpt-4o-mini
```

**4. Evaluation-as-contract** — `eval/quality_gate.py`'s `QualityGate` runs report-only or
blocking against versioned `Metrics` (answer-scoped and retrieval-scoped fields kept distinct,
fixed in Lot 13 after finding they were conflated).

**5. Observability built-in** — every retrieval/generation/guard step emits a real `TraceStep`
(`core/models/trace.py`); every governed run emits an `AuditEvent` when an `audit_sink` is
configured (`contracts/audit.py`, Lot 10).

---

## Architecture at a Glance

```
User Query
    ↓
[TENANT ISOLATION]  ← fail-closed identity check (Lot 11b)
    ↓
[SECURITY GUARD]    ← injection detection, policy check
    ↓
[RETRIEVAL]         ← vector + BM25 + RRF fusion (hybrid)
    ↓
[RERANKING]         ← cross-encoder, if configured
    ↓
[GENERATION]        ← LLM synthesis with retrieved context, via native or LangGraph engine
    ↓
[SECURITY GUARD]    ← answer-side check
    ↓
[REDACTION]         ← if configured
    ↓
[AUDIT + TRACE]     ← AuditEvent + TraceStep emission
    ↓
Answer + Citations
```

For the exact step order and which steps are optional (gated on whether the component is
configured), see `orchestration/CLAUDE.md` and
[architecture/runtime-flow.md](../architecture/runtime-flow.md).

---

## Current Status

V1 (Core RAG) is complete: hybrid retrieval, security guards, tenant isolation, audit trail,
document lifecycle (identity/idempotency/delete), quality gates, a hardened API/CLI, a
dependency/licence gate, and an immutable container build. On top of that, a full 18-lot
refactoring programme validated the `DocumentEngine` port against a second, real, structurally
different engine (LangGraph) and closed with a real pilot comparison. See
[docs/refactoring/README.md](../refactoring/README.md) for the full evidence trail, including
an honest list of what's still open (two escalated licence findings, an orphaned `Settings`
class, a few commands never executed against live infrastructure in the sandboxed environment
that built them).

---

## Owned vs. Delegated: V2-V5

Per [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5, every future version's
scope splits into what this framework builds natively and what it delegates to the selected
external engine via the `DocumentEngine` port:

| Version | Owned natively | Delegated to the external engine |
|---|---|---|
| **V2.0** | Policy Engine (real, shipped), tenant isolation (real, shipped) | — |
| **V2.1** | — | Multi-agent teams / collaborative agent orchestration |
| **V3.0** | A native `KnowledgeGraph` data model may be retained (undecided — see `memory/graph/knowledge_graph.py`'s own docstring) | GraphRAG traversal, multi-hop reasoning, community detection |
| **V3.1** | Cost-routing/caching logic, if built | — |
| **V3.2** | Drift detection / evaluation trigger | Fine-tuning execution itself |
| **V4** | Multi-tenant policy layering, audit retention, human-in-the-loop review | — |
| **V5.0** | Parsing/citation enrichment may stay native | VLM execution (image/video understanding) |

The practical consequence: building "V2 agentic" or "V3 GraphRAG" support means writing an
**adapter that calls the selected external engine** through the `DocumentEngine` port
(`contracts/engine.py`), the same way `adapters/llms/langgraph_engine.py` does today — not a
native coordinator/planner/retriever-agent runtime. A previous native prototype for exactly
those five agent roles was built once and removed (`docs/refactoring/lot-17-prototype-retirement.md`)
after a full consumer/test-coverage search found zero of either.

---

## Quick Start by Role

### For Developers
**Goal**: Build a RAG component quickly

1. Read [CLAUDE.md](../../CLAUDE.md) — project rules
2. Read [getting-started.md](./getting-started.md) — setup
3. Use the `/add-retriever` skill to implement a new retriever
4. Run `./scripts/check.sh full` before opening a PR

**Tools**: `@retrieval-specialist` subagent, `/design-retriever-fusion`, `/validate-architecture`.

### For Architects
**Goal**: Understand design decisions and validate systems

1. Read this document
2. Read [ADR-0001](../adr/0001-modular-architecture.md), [ADR-0002](../adr/0002-contracts-and-plugins.md), and [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) (the last one is the one that changed the roadmap — read it even if you've read the others before)
3. Review [architecture/overview.md](../architecture/overview.md)

**Tools**: `@architecture-reviewer` subagent, `/validate-architecture`, `/parallel-feature-analysis`.

### For Product Managers / Stakeholders
**Goal**: Understand capabilities, roadmap, and impact

1. Read this document ← you are here
2. Read [business-case.md](../business-case.md)
3. Review [ROADMAP.md](../../ROADMAP.md) — note its own ADR-0005 banner at the top

### For QA / Test Engineers
**Goal**: Evaluate and benchmark components

1. Read [validation-protocol.md](./validation-protocol.md) (the canonical validation-tier reference)
2. Use the `/prepare-evaluation` skill to create test suites

**Tools**: `@test-specialist` subagent, `/prepare-evaluation`, `/parallel-feature-analysis`.

### For DevOps / Platform Teams
**Goal**: Deploy, monitor, and scale the framework

1. Read [deployment.md](./deployment.md)
2. Read [backup-restore.md](./backup-restore.md)
3. Read [observability.md](./observability.md)

**Verified current capabilities**: an immutable multi-stage `Dockerfile` (Lot 16b, CI-built and
smoke-tested on every push), a manifest-driven `MRAG_MANIFEST_PATH`-configurable entrypoint
(`docker/server.py`), and documented (not yet live-executed in this sandboxed environment)
backup/restore/rollback runbooks — see `docs/guides/backup-restore.md` for the honesty note on
what has and hasn't been run against real infrastructure.

---

## Key Differentiators

### vs. LangChain / LlamaIndex

| Aspect | LangChain / LlamaIndex | This Framework |
|--------|-----------|-----------------|
| **Architecture** | Imperative chains / pipelines | Hexagonal, protocol-driven, layering enforced in CI |
| **Configuration** | Python code | YAML manifests |
| **Evaluation** | External tools (Ragas, etc.) | Built-in, contract-enforced quality gates |
| **Audit trail** | Manual logging | Structured `AuditEvent`s, PII/secret payload allowlist |
| **Multi-tenant** | Not a primary concern | Fail-closed tenant isolation, real Keycloak verifier |
| **Agent/graph orchestration** | Native, broad | Delegated to a selected engine (LangGraph today) via a vendor-neutral port — the differentiator is the governance/audit/portability layer around it, not a competing native runtime |
| **Observability** | Manual tracing | Automatic `TraceStep` + `AuditEvent` |

### vs. Proprietary Cloud Solutions (Bedrock / Vertex AI)

| Aspect | Cloud-native | This Framework |
|--------|------------------|-----------------|
| **Vendor lock-in** | High | None — works with any LLM/vector store; the execution engine itself is swappable (native/LangGraph) |
| **On-premise** | Typically no | Yes |
| **Cost transparency** | Often opaque | Per-query metrics, when configured |

---

## Business Impact

*(Business framing below is a planning input, not a verified engineering claim — treat the
numbers as estimates for discussion, not measured results.)*

- Faster per-project delivery by not rebuilding security/audit/evaluation each time.
- IP compounds across projects: adapters, manifests, and policies built once are reused.
- See [business-case.md](../business-case.md) for the full commercial argument and its own
  correction history (Lot 5 corrected unsupported delivered/security/compliance claims there).

---

## Get Started

```bash
# 1. Clone and setup
git clone https://github.com/HerbertGourout/modular-rag-framework.git
cd modular-rag-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[v1,dev]"

# 2. Verify setup
./scripts/check.sh quick

# 3. Read the essentials
cat CLAUDE.md
cat docs/guides/getting-started.md

# 4. Explore the code
ls -la src/modular_rag/
ls -la examples/simple_qa/
```

### Your first component

Use the `/add-retriever` skill: read the `Retriever` Protocol → implement → write unit +
contract tests → register in `orchestration/_default_factories.py` → select it in a manifest →
run `/validate-architecture`.

### Your first evaluation

Use the `/prepare-evaluation` skill: create a golden set → wire it through `eval/quality_gate.py`'s
`QualityGate` in report-only mode first → promote to blocking once a baseline is agreed.

### Your first policy

`security/policies/policy_engine.py`'s `PolicyEngine` and
`security/policies/tenant_isolation.py`'s `TenantIsolationPolicy` are real and shipped (not a
future item) — define roles/data classifications in YAML, wire a `tenant_policy` into your
manifest's `Container`, and test with `tests/unit/security/policies/test_tenant_isolation.py`
as a reference.

---

## Key Documents

| Document | Read when |
|----------|-----------|
| [CLAUDE.md](../../CLAUDE.md) | Starting — essential |
| [docs/refactoring/README.md](../refactoring/README.md) | Understanding what the 2026-08 refactoring programme changed |
| [ROADMAP.md](../../ROADMAP.md) | Understanding versions |
| [business-case.md](../business-case.md) | Justifying investment |
| [getting-started.md](./getting-started.md) | Setting up locally |
| [architecture/overview.md](../architecture/overview.md) | Deep dive |
| [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) | The decision that reshaped V2-V5 |
| [validation-protocol.md](./validation-protocol.md) | Running tests |

---

## FAQ

**Can I use this for production today?**
V1 is complete: hybrid retrieval, security, tenant isolation, audit trail, quality gates, a
hardened API, and a container build all exist and are tested. Read
`docs/refactoring/README.md` §5 for the honest list of what's still open before treating any
specific deployment as fully proven (e.g., some backup/restore commands are documented but
never executed against live infrastructure yet).

**Do I have to use LangChain?**
No. The framework orchestrates open-source components (Qdrant, rank-bm25, HuggingFace) directly,
and separately offers LangGraph as one of two selectable *execution engines* behind the
`DocumentEngine` port — using that engine doesn't mean adopting LangChain's own chain/agent
abstractions in your own code.

**Can I swap LLMs?**
Yes — change the generator's `type`/`config` in your manifest.

**What if I'm on-premise?**
Works fully on-premise with HuggingFace embedders + Qdrant + local LLMs.

**When will native multi-agent orchestration / GraphRAG ship?**
They won't, as native builds — per ADR-0005, that capability is delegated to the selected
external engine (LangGraph) via the `DocumentEngine` port, which already exists and is tested.
What ships going forward is deeper adapter integration with that engine, not a competing native
runtime.

**Can I contribute?**
See [CONTRIBUTING.md](../../CONTRIBUTING.md).

---

**Ready to build?** Start with [getting-started.md](./getting-started.md).
