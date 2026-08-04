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

Every component is exposed through a Protocol (`@runtime_checkable`). Implementations are registered in `orchestration/registry.py` and selected via YAML manifests. No direct Python wiring.

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

**Status:** Accepted  
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
3. Submit as MR with architecture team review.
4. Update status to "Accepted" after approval.

---

## Version Scope

- **ADR-0001, 0002, 0003**: Core architecture (V1-V5 stable)
- **ADR-0004**: Feature roadmap (V1→V5 progression) — partially superseded by ADR-0005
- **ADR-0005**: Product boundary pivot — engine-independent control plane, delegated orchestration

Future ADRs will be added as new major decisions arise (e.g., ADR-0006 for external engine selection per Lot 6, ADR-0007 for `DocumentEngine` contract freeze per Lot 7).

---

## References

- [ROADMAP.md](../ROADMAP.md) — Implementation timeline
- [CLAUDE.md](../../CLAUDE.md) — Development guidelines
- [Security Layers](../architecture/security.md) — Detailed security strategy
