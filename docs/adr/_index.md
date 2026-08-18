# Architectural Decision Records (ADRs)

This directory contains architectural decisions for the Modular RAG Framework. Each ADR documents a key design choice, rationale, and consequences.

---

## Index

### [ADR-0001: Modular Architecture with Six Planes](0001-modular-architecture.md)

**Status:** Accepted
**Date:** 2026-05-20

Organizes the system into six independent planes (Control, Ingestion, Knowledge, Reasoning, Safety, Evaluation) with strict dependency rules. Each plane communicates only through contracts (Python Protocols), enabling component swappability and testability.

**Key insight:** No plane imports from another plane's implementation. All communication via `contracts/` and `core/models/`.

---

### [ADR-0002: Contracts and Plugins Pattern](0002-contracts-and-plugins.md)

**Status:** Accepted  
**Date:** 2026-05-22

Every component is exposed through a Protocol (`@runtime_checkable`). Implementations are registered as factories in `app/default_factories.py` and wired by `orchestration/registry.py`'s generic `ComponentRegistry`, selected by name in YAML manifests. No direct Python wiring.

**Key insight:** Contracts first, implementation second. Tests verify Protocol conformance before deployment.

---

### [ADR-0003: Security and Governance](0003-security-and-governance.md)

**Status:** Accepted  
**Date:** 2026-06-19

Seven-layer security strategy: Permissions → Hooks → Policies → Segmentation → Secrets → MCP → Audit.  
Distinguishes Safety (prompt injection, PII) from Security (RBAC, policies, enforcement).

**Key insight:** Safety ≠ Security. Governance is proactive (prevent bad queries) not just reactive.

---

### [ADR-0004: Strategic Features (V1→V5)](0004-strategic-features-v1-v5.md)

**Status:** Superseded (partial) — see ADR-0005  
**Date:** 2026-06-20

Roadmap integrating 8 transformational capabilities across versions:
- **V1.1**: Evaluation-as-Contract
- **V1.2**: Compliance Audit Trail
- **V2.0**: Policy Engine
- **V2.1**: Multi-Agent Teams
- **V3.0**: Knowledge Graphs
- **V3.1**: Cost Optimization
- **V3.2**: Fine-Tuning Loop
- **V4.1**: Multi-Language + Cultural Reasoning

**Key insight:** Do not compete with LangChain on breadth. Compete on depth in governance, compliance, cost optimization, and fine-tuning.

---

### [ADR-0005: Document-AI Control Plane Product Boundary](0005-document-ai-control-plane-boundary.md)

**Status:** Accepted  
**Date:** 2026-08-03 (accepted 2026-08-04)

Redraws the product boundary: own engine-independent governance, audit, evaluation, tenant
isolation, and manifest/config as the durable differentiator; delegate generic multi-agent
orchestration, GraphRAG traversal, fine-tuning platform mechanics, and multimodal execution to
a selected external engine via a new `DocumentEngine` port. Native V1 (`RAGEngine`) becomes a
bounded reference adapter with explicit exit criteria, not the long-term core.

**Key insight:** Partially supersedes ADR-0004 — V1.1/V1.2/V2.0 are retained natively; V2.1,
V3.0, V3.2, and V5.0 are redirected from "build in-house" to "delegate via adapter."

---

### [ADR-0006: External Engine Selection — LangGraph](0006-external-engine-selection.md)

**Status:** Accepted  
**Date:** 2026-08-04

Recommends LangGraph as the external engine the `DocumentEngine` port (Lot 7) adapts to, from an
executed spike comparing LangGraph and LlamaIndex Workflows against a governed-QA use case and
an 8-dimension capability checklist. Full evidence in
[`docs/refactoring/lot-6-spike/`](../refactoring/lot-6-spike/).

**Key insight:** LangGraph wins on zero-instrumentation streaming, footprint, and structural
legibility; loses clearly on cancellation (LlamaIndex has a native `cancel_run()` API) — the gap
doesn't change the recommendation because Lot 7 has to build an engine-neutral cancellation
contract regardless of which engine is picked.

---

### [ADR-0007: Layer Boundaries and Control-Plane Activation](0007-layer-boundaries-and-control-plane-activation.md)

**Status:** Accepted
**Date:** 2026-08-07

Proposes the concrete dependency model and activation path needed to make ADR-0005 operational:
orchestration-owned container, application facade for API/CLI, manifest wiring for every owned
control-plane capability, separation of runnable presets from blueprints, and removal of
never-functional legacy manifest fields.

**Key insight:** A capability is not delivered merely because its class exists; it must be
reachable through a supported entry point, manifest-wired where applicable, and covered by that
path's tests.

---

### [ADR-0008: Offline Evaluation and Honest Engine Activation](0008-offline-evaluation-and-engine-activation.md)

**Status:** Accepted
**Date:** 2026-08-08

Separates golden-set evaluation/regression gates from online answer execution and makes runtime
engine incompatibilities fail startup. LangGraph manifests cannot claim audit, policy-engine,
review or telemetry controls until a tested bridge consumes them.

**Key insight:** a gold-dependent quality score cannot truthfully block an ordinary production
question, and a selected engine must never silently ignore a declared control.

---

### [ADR-0009: VectorIndexer Sub-Protocol and Dimension Reconciliation](0009-vector-indexer-dimension-reconciliation.md)

**Status:** Accepted
**Date:** 2026-08-11

Adds an opt-in `VectorIndexer(Indexer, Protocol)` sub-protocol so dimension-sensitive stores
(Qdrant today) can reconcile their configured `vector_size` against the wired embedder's real
output dimension — derived when unset, validated when explicit, rejected with
`ConfigurationError` before any collection is created or used (including against an
already-existing collection, and on a retry after a prior failure), and named-vector collections
rejected cleanly rather than with an opaque `AttributeError`. `wire()` hands the embedder off via
`bind_embedder()`, a real protocol method — not a private attribute an implementation might
ignore — and `QdrantStore` defers the actual reconciliation into its own lazy client-creation
path, so a custom embedder's real dimension is never computed until the pipeline actually needs a
live store.

**Key insight:** non-vector `Indexer` implementations are entirely unaffected — reconciliation is
opt-in via a narrow sub-protocol, not a field added to `Indexer` itself.

---

### [ADR-0010: HealthCheckable Port and Readiness Semantics](0010-health-checkable-and-readiness-semantics.md)

**Status:** Accepted
**Date:** 2026-08-17

Documents the `HealthCheckable` port, `DependencyHealth`/`ReadinessReport` models, the
three-state (`healthy`/`degraded`/`unready`) readiness contract, the role-based-plus-capability
criticality rules driving `UNREADY`, probe budget/side-effect constraints (no retries, no writes,
bounded timeouts, no LLM calls), the exception-detail non-leak requirement on the unauthenticated
`/ready` route, and compatibility rules for a future implementation. Ratifies a design already
shipped rather than gating it behind a future decision — written in response to a Codex review
finding that the new public port had no recorded ADR.

**Key insight:** criticality is decided by reading the actual current exception-handling code
path (does this failure crash `/answer` today?), never by an a-priori guess at a component's
importance — and a capability-level rule (no retrieval leg confirmed usable) can escalate
readiness beyond what any single role's exception-based criticality would catch alone.

---

## Decision Making Process

1. **Identification**: Problem identified in sprint planning, client feedback, or architecture review.
2. **Context**: Document the problem, alternatives considered, and trade-offs.
3. **Decision**: State the chosen solution clearly.
4. **Consequences**: List positive outcomes, risks, and mitigations.
5. **Status**: Track through Accepted → Implemented → Superseded (if applicable).

---

## How to Propose an ADR

1. Create `docs/adr/000X-title.md` following this template:
   ```markdown
   # ADR-000X — Title
   
   **Status:** Proposed  
   **Date:** YYYY-MM-DD  
   **Authors:** Your Name
   
   ---
   
   ## Context
   (Explain the problem)
   
   ## Decision
   (Explain the solution)
   
   ## Consequences
   (Positive, Negative, Mitigations)
   ```

2. Link from this index.
3. Submit as a GitHub PR with architecture review.
4. Update status to "Accepted" after approval.

---

## Version Scope

- **ADR-0001, 0002, 0003**: Core architecture (V1-V5 stable), each with a short 2026-08 amendment
  note correcting specific claims that ADR-0005 or subsequent lots superseded — the underlying
  decisions in all three remain accepted and unchanged.
- **ADR-0004**: Feature roadmap (V1→V5 progression) — superseded (partial) by ADR-0005; archived
  in full at [docs/archive/0004-strategic-features-v1-v5.md](../archive/0004-strategic-features-v1-v5.md),
  this path now a stub.
- **ADR-0005**: Product boundary pivot — engine-independent control plane, delegated orchestration. Accepted.
- **ADR-0006**: External engine selection (LangGraph). Accepted.
- **ADR-0007**: Layer boundaries and control-plane activation. Accepted.
- **ADR-0008**: Offline evaluation and honest engine activation. Accepted.
- **ADR-0009**: `VectorIndexer` sub-protocol and dimension reconciliation. Accepted.
- **ADR-0010**: `HealthCheckable` port and readiness semantics. Accepted.

All ten ADRs are Accepted as of this writing — none are in Proposed status. Future ADRs will be
added as new major decisions arise; per this project's own rule
([CLAUDE.md §07](../../CLAUDE.md#07--security-rules)), any new top-level module, layer boundary,
or contract modification requires one.

---

## References

- [ROADMAP.md](../../ROADMAP.md) — Implementation timeline
- [CLAUDE.md](../../CLAUDE.md) — Development guidelines
- [Security Layers](../architecture/security.md) — Detailed security strategy
