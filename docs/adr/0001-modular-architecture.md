# ADR-0001 — Modular Architecture with Six Planes

**Status:** Accepted  
**Date:** 2026-05-20  
**Authors:** Herbert Gourout, Publicis Data Specialists

> **Amendment, 2026-08 (not a status change — the six-plane decision itself is unchanged and
> still accepted):** the "Reasoning" plane row below lists `agents/` alongside "planning,
> retrieval orchestration... generation" as this project's own native reasoning implementation.
> Per [ADR-0005](0005-document-ai-control-plane-boundary.md) §5.2 (accepted 2026-08-04), generic
> multi-agent orchestration is delegated to a selected external engine — `agents/` today hosts
> engine-delegation adapter-integration code, not a native planner/coordinator runtime; the five
> native agent classes this ADR originally had in mind were removed in
> [Lot 17](../refactoring/lot-17-prototype-retirement.md). The six-plane *boundary* structure
> itself (Control/Ingestion/Knowledge/Reasoning/Safety/Evaluation, contracts-only communication,
> no plane importing another plane's implementation) is unaffected and remains exactly as decided
> below — only which concrete modules populate the Reasoning plane's agent-orchestration slice
> changed.

---

## Context

Building a production-grade RAG system that needs to evolve from a simple retrieve-then-generate pipeline (V1) to a full compound AI system with graph memory, governance, and multimodal reasoning (V3–V5) without rewriting the core.

The main risks identified at design time:
- **Lock-in**: choosing a monolithic pipeline makes it hard to swap components.
- **Coupling**: business logic bleeds into LLM adapters or vice versa.
- **Untestability**: without clear interfaces, components cannot be tested in isolation.

---

## Decision

Organise the system into **six planes**, each with a single responsibility:

| Plane | Responsibility | Modules |
|---|---|---|
| **Control** | Manifests, routing, policy, audit | `contracts/manifests`, `orchestration/`, `security/policies/` |
| **Ingestion** | Parsing, normalisation, chunking, enrichment | `ingestion/` |
| **Knowledge** | Index, vector store, graph store, reranking | `retrieval/`, `adapters/vectorstores/`, `adapters/graphstores/` |
| **Reasoning** | Planning, retrieval orchestration, agents, generation | `orchestration/engine`, `agents/`, `generation/` |
| **Safety** | Adversarial detection, poisoning defence, policy enforcement | `security/` |
| **Evaluation** | Benchmarks, metrics, scoring, regression | `eval/` |

Within each plane, all components are exposed through **contracts** (`src/modular_rag/contracts/`) — Python Protocols decorated with `@runtime_checkable`. No plane imports from another plane's implementation; they communicate only through contracts and `core/models/`.

---

## Consequences

**Positive**
- Any component can be replaced by implementing the matching Protocol.
- The engine (`orchestration/engine.py`) depends only on contracts, never on concrete classes.
- Contract tests (`tests/contract/`) verify that any adapter satisfies the protocol.

**Negative / risks**
- More initial boilerplate (Protocol per capability).
- Developers must understand the layering rule before contributing.

**Mitigations**
- CLAUDE.md documents the dependency rule.
- The registry (`orchestration/registry.py`) enforces wiring declaratively.
- Factory registration is centralised in `app/default_factories.py`.
