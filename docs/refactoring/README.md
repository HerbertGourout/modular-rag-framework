# Refactoring Programme — Reading Guide

This is the index for the original 18-lot engine-agnostic control-plane refactoring programme
and its follow-on lots (`docs/refactoring-plan.md`). Lots 0-18 were executed 2026-08-03 through
2026-08-05; Lot 19 followed, Lot 20 shipped 2026-09-08 and is now fully complete (ADR-0016
Accepted 2026-09-09), and
Lots 21–22 are planned by accepted ADR-0015; Lot 21's Lot-20 dependency is now satisfied and its
own contract ADR ([ADR-0017](../adr/0017-engine-independent-assurance-contract.md)) is drafted,
but not yet accepted — implementation has not started. It answers: **what
happened, in what order, why, and where's the proof** — for anyone reading this repository
after the fact, whether that's a new team member, a reviewer, or a future Claude Code session
picking the work back up.

It replaces nothing — `docs/refactoring-plan.md` remains the authoritative plan-and-tracker
document (scope, gap matrix, decision log, acceptance criteria). This guide is the *entry
point* into that document and the per-lot evidence or scope files it links to, for someone who
doesn't yet know where to start.

---

## 1. What this programme was, in three sentences

[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) changed what this framework
builds natively versus delegates to a selected external engine: it owns governance, audit,
evaluation, config/manifests, tenant isolation, and portability, and delegates generic
multi-agent orchestration and GraphRAG traversal to that engine (LangGraph,
[ADR-0006](../adr/0006-external-engine-selection.md)) via a vendor-neutral `DocumentEngine`
port.

The original 18 lots executed that pivot — from "accept the ADR" through
"validate the port against a second real engine and close the programme" — and follow-on lots
record material boundaries found after that closure.

**If you read nothing else, read `docs/refactoring-plan.md` §1** (Product boundary and target
architecture) and **ADR-0005** — everything else is downstream of that one decision.

---

## 2. Recommended reading order, by why you're here

### "I need to understand what changed and why, fast"
1. This section (§1 above).
2. §3's phase summaries below — four paragraphs, one per phase.
3. §5's "what's still open" — the honest, unresolved parts.

### "I'm extending this codebase and need to know the current architecture"
1. [docs/adr/0005-document-ai-control-plane-boundary.md](../adr/0005-document-ai-control-plane-boundary.md)
   and [0006-external-engine-selection.md](../adr/0006-external-engine-selection.md) — the two
   decisions everything else follows from.
2. [docs/architecture/document-engine-contract.md](../architecture/document-engine-contract.md)
   — the `DocumentEngine` port's compatibility/versioning policy, if you're touching either
   engine adapter.
3. [docs/architecture/structure.md](../architecture/structure.md) — corrected during Lot 17 to
   match what's actually in the codebase today, not what an earlier draft aspired to.
4. The lot decision record for whichever capability you're touching (§4's table has the
   full map).

### "I'm reviewing this programme for sign-off" (architecture / security / operations / legal / business-quality)
1. [docs/refactoring/lot-18-pilot-and-closure.md](lot-18-pilot-and-closure.md) — the closure
   lot. Its "What this lot cannot do" section explains directly why sign-off isn't
   self-granted and what it needs from you specifically.
2. §5 below — every open item, in one place, with the lot that found it.
3. `docs/refactoring-plan.md` §6 (Acceptance criteria by stage) and §9 (Final completeness
   checklist) — the actual bar each lot was held to, and which checklist items remain
   unchecked pending your review.

### "I want to verify a specific claim, not read a narrative"
Go straight to `docs/refactoring-plan.md`'s **gap matrix** (§2) — every row is either
`~~struck through~~` (resolved, with the lot and evidence file that proves it) or still open
(with the lot assigned to address it, or explicitly "unscheduled").

---

## 3. The four phases, in one paragraph each

**Phase A — Control and evidence (Lots 0-5).** Established who decides what (sole authority,
Herbert Gourout), accepted ADR-0005, realigned every Claude/repository instruction file to
match it, built a reproducible local environment and a real CI (compilation, layering, a
ratcheted mypy baseline, a wheel build, a clean-install smoke test), wrote characterization
tests for every public surface before changing any of it (finding a real bug: `POST /answer`
returned 422 on every documented call), and corrected every unsupported delivered/security/
compliance claim in the docs. Evidence: `lot-0` through `lot-5`.

**Phase B — Architecture foundations (Lots 6-10).** Selected LangGraph over LlamaIndex
Workflows via a real executed spike, not a docs comparison (ADR-0006); built the
`DocumentEngine` port with zero vendor types leaking into the contract and a semantic
conformance suite (not just `isinstance` checks); wrapped the existing `RAGEngine` in a
`NativeEngineAdapter` with an honest, empty capability set; made manifests strict, versioned,
and capable of `${VAR}`/`secret://` interpolation (opt-in, not wired into the default
pipeline-loading path — a distinction that matters, see §5); built the trace/audit schema
foundation. Evidence: `lot-6` through `lot-10`.

**Phase C — Enterprise correctness (Lots 11a-14).** Threat model and data-classification
policy, then fail-closed tenant isolation with a real Keycloak token verifier; redaction, a
GUARD_DECISION audit event on every governance denial, and a human-review gate; a document
lifecycle plane (identity, idempotency, delete — closing a gap where `RAGEngine` had no
`delete()` at all); index reconciliation and schema versioning (finding and fixing `QdrantStore`
silently dropping `tenant_id`, which had defeated tenant isolation for the real vector-store
path); backup/restore/erasure proven with a genuine executed round-trip, not a written
procedure; corrected metric vocabulary and a benchmark failure-masking bug; timeouts,
retry/circuit-breaker primitives, and `threading.Lock` on every in-memory store with a genuine
race. Evidence: `lot-11a` through `lot-14`.

**Phase D — Portability and delivery (Lots 15-18).** Built `LangGraphEngineAdapter`, the
second `DocumentEngine` implementation, and proved the port genuinely engine-neutral by running
it against a structurally different engine, not a wrapper of the native one (finding and fixing
a hexagonal-layering violation and a governance-parity bug along the way). Hardened the API
(auth, rate limits, typed-safe errors) and CLI (exit codes), finding that `RAGEngine.retrieve()`
had silently bypassed tenant isolation the whole time. Built a single version source, a
dependency licence gate, an SBOM, and an immutable container build — escalating two real
licence/legal findings rather than deciding them unilaterally. Wrote deployment/backup/restore/
rollback runbooks, finding that `app/settings.py`'s entire `Settings` class was never actually
wired into the pipeline. Removed an entire dead agent/routing/planning prototype cluster with
zero test coverage and zero consumers. Closed with a real native-vs-external-engine pilot
comparison that found a *second* governance-parity bug the per-lot tests had missed. Evidence:
`lot-15` through `lot-18`.

---

## 4. Every lot, one line each

| Lot | What it did | Evidence |
|---|---|---|
| 0 | Baseline SHA, decision authority, evidence locations | [lot-0-baseline.md](lot-0-baseline.md) |
| 1 | Accepted ADR-0005 | folded into Lot 2's evidence, below |
| 2 | Realigned every Claude/repo instruction file to ADR-0005 | [lot-2-claude-realignment.md](lot-2-claude-realignment.md) |
| 3 | Reproducible `.venv`, mypy baseline, real CI | [lot-3-baseline-and-ci.md](lot-3-baseline-and-ci.md) |
| 4 | Characterization tests; found the `/answer` 422 bug | [lot-4-public-surface-part1.md](lot-4-public-surface-part1.md), [part2](lot-4-part2-metrics-deletion-fallback.md) |
| 5 | Corrected unsupported delivered/security/compliance claims | [lot-5-capability-truth.md](lot-5-capability-truth.md) |
| 6 | LangGraph vs. LlamaIndex Workflows spike; ADR-0006 | [lot-6-spike/](lot-6-spike/) |
| 7 | `DocumentEngine` port, semantic conformance suite | [lot-7-document-engine-contract.md](lot-7-document-engine-contract.md) |
| 8 | `NativeEngineAdapter`; fixed the `/answer` bug for real | [lot-8-native-adapter.md](lot-8-native-adapter.md) |
| 9 | Strict versioned manifests, `${VAR}`/`secret://` resolution | [lot-9-versioned-config.md](lot-9-versioned-config.md) |
| 10 | Trace/audit schema foundation, `AuditSink` | [lot-10-trace-audit-foundation.md](lot-10-trace-audit-foundation.md) |
| 11a | Threat model, data-classification policy | [lot-11a-threat-model-data-classification.md](lot-11a-threat-model-data-classification.md) |
| 11b | Fail-closed tenant isolation, Keycloak verifier | [lot-11b-identity-tenant-propagation.md](lot-11b-identity-tenant-propagation.md) |
| 11c | Redaction, GUARD_DECISION audit events, human review | [lot-11c-redaction-audit-human-review.md](lot-11c-redaction-audit-human-review.md) |
| 12a | Document lifecycle: identity, idempotency, delete | [lot-12a-document-lifecycle.md](lot-12a-document-lifecycle.md) |
| 12b | Index reconciliation; fixed `QdrantStore` tenant_id bug | [lot-12b-index-reconciliation.md](lot-12b-index-reconciliation.md) |
| 12c | Backup/restore/erasure, genuinely executed round-trip | [lot-12c-backup-restore-erasure.md](lot-12c-backup-restore-erasure.md) |
| 13 | Corrected metric vocabulary, benchmark failure-masking | [lot-13-quality-measurement-plane.md](lot-13-quality-measurement-plane.md) |
| 14 | Timeouts, retry/circuit-breaker, thread-safety locks | [lot-14-reliability-concurrency.md](lot-14-reliability-concurrency.md) |
| 15 | `LangGraphEngineAdapter`, the second `DocumentEngine` | [lot-15-langgraph-adapter.md](lot-15-langgraph-adapter.md) |
| 16a | API auth/rate-limits/errors, CLI exit codes | [lot-16a-api-cli-hardening.md](lot-16a-api-cli-hardening.md) |
| 16b | Version source, licence gate, SBOM, container build | [lot-16b-supply-chain.md](lot-16b-supply-chain.md) |
| 16c | Deployment/backup/restore/rollback runbooks | [lot-16c-deployment-runbooks.md](lot-16c-deployment-runbooks.md) |
| 17 | Removed the dead agent/routing/planning prototype cluster | [lot-17-prototype-retirement.md](lot-17-prototype-retirement.md) |
| 18 | Pilot comparison, CI hardening, programme closure | [lot-18-pilot-and-closure.md](lot-18-pilot-and-closure.md) |
| 19 | Layer-boundary correction (`Container`/factories moved, facade enforced) and control-plane manifest activation (ADR-0007) | [lot-19-layer-boundary-stabilization.md](lot-19-layer-boundary-stabilization.md) |
| 20 | **Planned:** fail-closed data classification and LLM/embedding egress control | [authoritative scope and acceptance criteria](../refactoring-plan.md#phase-e--data-protection-and-controlled-model-egress-lot-20) |
| 21 | **Planned:** engine-independent assurance levels and conformance report | [lot-21-engine-independent-assurance-contract.md](lot-21-engine-independent-assurance-contract.md) |
| 22 | **Proposed:** wrap and measure an existing external application | [lot-22-external-application-adapters-and-conformance.md](lot-22-external-application-adapters-and-conformance.md) |

A follow-on audit after Lot 18's closure found two structural gaps Lots 0-18 hadn't
caught: the published dependency direction didn't match the real one (`orchestration/`
imported `app.Container`), and several owned governance/audit/quality capabilities were
implemented and tested but not reachable through any manifest. Lot 19
([ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md)) is the
correction — engineering-complete as of 2026-08-07, same sign-off caveat as Lots 0-18.

Lot 20 (engineering-complete 2026-09-08, see
[lot-20-data-classification-egress-control.md](lot-20-data-classification-egress-control.md))
closes the outbound-data gap where post-generation redaction cannot prevent document/chunk
content, or the query text embedded to retrieve it, from reaching an external embedder/generator:
a fail-closed `governance.egress_policy` gates embedding (both ingestion and query-time
retrieval), reranking, and generation on both the native and LangGraph engines — mandatory, not
optional, the moment a manifest wires one of this framework's own known remote provider types
(`openai`/`anthropic`/`openai-embeddings`); a manifest that doesn't cover one fails to load
(Codex review pass 1, HIGH-001). It is local-first (a `local: true` provider always allowed,
zero configuration needed for a purely local pipeline) and provider-neutral (profiles are
manifest data, not hardcoded vendor logic). All three shipped presets now configure it, and its
[ADR-0016](../adr/0016-provider-egress-control.md) is Accepted (2026-09-09) — see the evidence
doc for the complete list of what did and did not ship.

Lots 21–22 are planned scope documents, not implementation evidence. They become actionable only
after their dependencies are complete: Lot 20's own sign-off/ADR gap is now closed (ADR-0016
Accepted 2026-09-09); Lot 21's own focused contract ADR
([ADR-0017](../adr/0017-engine-independent-assurance-contract.md)) is drafted, defining honest
assurance levels and reports, but not yet accepted — implementation starts only once it is, then
Lot 22 tests them by wrapping an existing application without reconstructing it.

---

## 5. What's still open — the honest list

This table preserves findings from the programme and records their current disposition. Rows now
marked resolved remain here for traceability rather than being silently deleted.

| Item | Status | Lot |
|---|---|---|
| `pymupdf`'s AGPL-3.0/Artifex Commercial dual licence | Escalated; Herbert Gourout confirmed "leave as-is for now," not resolved | [16b](lot-16b-supply-chain.md) |
| 56 research PDFs' unverified per-paper redistribution rights | Escalated; same "leave as-is for now" confirmation; catalogued (not resolved) in Lot 17 | [16b](lot-16b-supply-chain.md), [17](lot-17-prototype-retirement.md) |
| `app/settings.py`'s unused `Settings` class | **Resolved in ADR-0007 Étape 8:** removed; manifest/env interpolation and SDK variables are the real configuration paths | [16c](lot-16c-deployment-runbooks.md), [19](lot-19-layer-boundary-stabilization.md) |
| `.gitlab-ci.yml`/`.gitlab/` removal | **Resolved:** neither path exists in the current tree | [17](lot-17-prototype-retirement.md) |
| `memory/graph/knowledge_graph.py` — data model or delegated traversal? | **Resolved in ADR-0007 Étape 8:** removed after confirming zero consumers; GraphRAG remains delegated | [17](lot-17-prototype-retirement.md), [19](lot-19-layer-boundary-stabilization.md) |
| LangGraph adapter emits no audit evidence | `ApplicationService` now supplies the caller above the port, but its event-to-`AuditSink` bridge remains open | [15](lot-15-langgraph-adapter.md), [19](lot-19-layer-boundary-stabilization.md) |
| Overload/soak load-test script never executed against live infra | Script exists (`scripts/loadtest_answer.py`), never run — no live deployment target in this environment | [16c](lot-16c-deployment-runbooks.md) |
| Postgres/Qdrant backup-restore commands never executed against live infra | Commands are correct against each system's real documented tooling, unexecuted here | [16c](lot-16c-deployment-runbooks.md) |
| CI `container-build`/`supply-chain` jobs never executed in this environment | No `docker` binary here; the next GitHub Actions run is the real verification | [16b](lot-16b-supply-chain.md) |
| `manifests/production/_index.md` cannot be edited | Hard `permissions.deny` on `manifests/production/**`; confirmed intentional (V4+ scope), blocked two separate edit attempts | [19](lot-19-layer-boundary-stabilization.md) |
| API/CLI engine selection | Resolved: API and CLI use `load_application()` and honor `engine.adapter` for answer execution | [19](lot-19-layer-boundary-stabilization.md) |
| `IndexReconciler` exposure | **Partly resolved:** `mrag reconcile --mode check|repair` and Python use exist; HTTP API/manifest role do not | [19](lot-19-layer-boundary-stabilization.md) |
| **Final sign-off** (architecture/security/operations/legal/business-quality) | **Not self-granted** — reserved for Herbert Gourout | [18](lot-18-pilot-and-closure.md), [19](lot-19-layer-boundary-stabilization.md) |

---

## 6. Key new capabilities, and where they live

| Capability | Code | Governing ADR/lot |
|---|---|---|
| Engine-neutral execution port | `src/modular_rag/contracts/engine.py` | ADR-0005 §5.2, Lot 7 |
| Native engine adapter | `src/modular_rag/orchestration/native_engine.py` | Lot 8 |
| LangGraph engine adapter | `src/modular_rag/adapters/llms/langgraph_engine.py` | ADR-0006, Lot 15 |
| Fail-closed tenant isolation | `src/modular_rag/security/policies/tenant_isolation.py` | Lot 11b |
| Compliance audit trail | `src/modular_rag/contracts/audit.py`, `security/audit/`, `adapters/audit/` | Lot 10, 11c |
| Document lifecycle (identity/idempotency/delete) | `src/modular_rag/contracts/lifecycle.py`, `ingestion/lifecycle/` | Lot 12a-c |
| Quality gates | `src/modular_rag/eval/quality_gate.py` | Lot 13 |
| API auth/rate-limits/errors | `src/modular_rag/api/errors.py`, `api/middleware.py` | Lot 16a |
| Dependency licence gate | `scripts/check_licenses.py`, `.claude/license-baseline.txt` | Lot 16b |
| Immutable container build | `Dockerfile`, `docker/server.py` | Lot 16b |
| Deployment/backup/restore runbooks | `docs/guides/deployment.md`, `docs/guides/backup-restore.md` | Lot 16c |
| Research evidence catalogue | `docs/research/EVIDENCE-CATALOGUE.md` | Lot 17 |
| Native-vs-external engine pilot | `scripts/pilot_engine_comparison.py` | Lot 18 |

---

## 7. Relationship to the general framework onboarding guide

[docs/onboarding.md](../onboarding.md) answers "who should read what, in what order" for the
framework as a whole, organized by role (developer, tech lead, consultant, security officer).
This guide is narrower and newer: it's specifically about the refactoring programme's own
output. If you're new to the framework in general, start with `docs/onboarding.md`; if you
specifically need to understand *this programme*, start here.
