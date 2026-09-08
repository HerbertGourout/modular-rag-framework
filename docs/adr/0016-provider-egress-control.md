# ADR-0016 — Provider Data-Egress Control Boundary

**Status:** Proposed — drafted 2026-09-08 in response to Codex review pass 1's HIGH-004 finding
on Lot 20 (`.review/codex-review.md`, `.review/handoff.md`); not self-accepted. Acceptance,
rejection, or revision is Herbert Gourout's decision, per
[`docs/refactoring/lot-0-baseline.md`](../refactoring/lot-0-baseline.md) §2's sole decision
authority — the same convention every other ADR in this repository has followed.

**Date:** 2026-09-08

**Authors:** Drafted by Claude Code during Lot 20 corrective remediation, at explicit user
instruction (Codex review pass 1 named this contract's missing ADR as a required-scope gap; the
user chose "draft a Proposed ADR for review" over leaving the gap undocumented).

---

## Context

`docs/architecture/threat-model.md` and `docs/architecture/data-classification-policy.md` both
named a real, longstanding gap: `PatternRedactor` (`security/redaction/patterns.py`) runs on
*generated answer text*, after the model has already produced a response. Nothing in this
codebase stopped raw query text, retrieved chunk content, document content, or embedding input
from reaching an external embedder or generator *before* that point. `docs/refactoring-plan.md`
named this Lot 20 ("Data Classification and LLM Egress Control") and — per its own first
required-scope bullet — called for an ADR before implementing the contract. Implementation
proceeded first, from the already-accepted [ADR-0015](0015-portable-assurance-and-external-application-boundary.md)
§5 ("data protection is part of assurance") and explicit task instruction, without waiting on
this ADR; Codex review pass 1 flagged that ordering as a real gap (HIGH-004), not merely a
documentation nicety, since a new public security contract now exists with no architectural
decision record behind it. This ADR is the corrective step: it documents, for human review, the
decision the implementation already embodies, so it can be formally accepted, revised, or
rejected rather than left implicit.

Full implementation evidence: [`docs/refactoring/lot-20-data-classification-egress-control.md`](../refactoring/lot-20-data-classification-egress-control.md).

## Decision

### 1. What this contract guarantees

`contracts/egress.py` defines `EgressPolicy` — a Protocol with one method,
`check(classification, provider, operation) -> EgressDecision` — evaluated immediately before an
owned component sends content to an external provider. `security.policies.egress_policy.
ManifestEgressPolicy` is the reference implementation: a manifest-configured map of
`provider -> {local: bool, max_classification?: DataClassification}`, plus a
`default_classification` applied to unclassified input.

The guarantee, when `governance.egress_policy` is configured: content is checked against a
manifest-declared ceiling before `Embedder.embed()` (both document/chunk ingestion and
query-time embedding for retrieval), `Reranker.rerank()`, and `Generator.generate()`, on both the
native engine and the LangGraph delegated-engine handoff. A `local: true` provider is always
allowed, any classification — the local/offline profile remains the unconditional safe fallback.
An unknown provider, or content whose classification (or, absent one, the policy's own
`default_classification`) exceeds a provider's declared ceiling, is denied — raising
`EgressDeniedError`, a `SecurityError` subclass, before the guarded call executes.

### 2. Opt-in, not a default-closed gate — a deliberate, now-confirmed choice

`governance.egress_policy` is optional, mirroring `tenant_policy`/`redactor`'s existing
optionality. **Absent from a manifest, this control is inert and behavior is unchanged from
before this ADR/lot existed** — including for a manifest wiring a remote provider with no
classified content protection at all. This was flagged explicitly (Codex review pass 1,
HIGH-001: "remote providers still run with no manifest egress permission") as arguably
contradicting the plain-language acceptance criterion "no owned external path can receive
classified content unless the manifest explicitly permits it."

The alternative — failing closed by default whenever a manifest wires any non-local provider,
regardless of whether `governance.egress_policy` is configured — was considered and rejected for
this decision. It would break all three shipped presets (`local-hybrid-rag.yaml`,
`secure-enterprise-rag.yaml`, `langgraph-rag.yaml`, all wiring `generator.type: openai`/
`anthropic` with no egress policy) and `examples/simple_qa/`, directly conflicting with
[CLAUDE.md](../../CLAUDE.md) §01's non-negotiable priority ("must not break
`examples/simple_qa/`"). Confirmed by Herbert Gourout, 2026-09-08, in response to Codex review
pass 1's HIGH-001: **accept the residual risk of an unconfigured pipeline having no egress
protection, keep the opt-in design.** An operator handling any classified/sensitive content
through a remote provider must configure `governance.egress_policy` explicitly — this is a
deployment responsibility this contract makes possible to discharge, not one it enforces
unconditionally by itself. `docs/guides/`-level operator documentation should say this plainly
wherever `governance.egress_policy` is documented.

### 3. Out of scope for this contract

- **Pseudonymization / reversible token mapping.** An *allowed* call still sends real,
  unmodified content. `docs/refactoring-plan.md`'s original Lot 20 scope described locally
  pseudonymizing PII/secrets before an allowed remote call, with an encrypted, short-lived,
  audit-invisible token mapping — not built. `PatternRedactor` remains the only content-mutating
  control in this codebase, and it is answer-side only.
- **Provider capability richness.** A profile is `{local, max_classification}` only — no
  retention, residency, feature-eligibility, or DPA/subprocessor modeling.
  `docs/refactoring-plan.md`'s own gap-matrix already scopes that as a deployment-owner/DPO
  decision code cannot infer, not something this contract should attempt.
- **Non-owned-adapter outbound connections.** PostgreSQL (audit/lifecycle/feedback/review sinks)
  and any other outbound connection this framework makes are untouched — this contract covers
  only the `Embedder`/`Generator`/`Reranker`/delegated-`DocumentEngine` boundary.
- **Query content classification.** `core.models.query.Query` carries no `classification` field.
  Query-time embedding is checked (Codex review pass 1, HIGH-002 closed this), but always against
  the policy's `default_classification` — there is no mechanism for a caller to declare "this
  specific question is confidential," and building automatic inference is explicitly named as
  unassigned-to-any-lot in `docs/architecture/data-classification-policy.md` §5.

### 4. Compatibility and lifecycle expectations

- `EgressOperation` (`EMBED`/`GENERATE`/`RERANK`) is the complete set of owned external-provider
  boundaries this contract recognizes today. A future owned boundary that transmits content
  (e.g. a remote tool-call adapter) should add a new `EgressOperation` value rather than overload
  an existing one.
- `provider` is the manifest's `ComponentConfig.type` string, not a component's own `.name()` —
  chosen because several adapters (`HuggingFaceEmbedder`, `OpenAIEmbedder`) make `.name()`
  dynamic/model-specific, which would make a policy-config key silently drift whenever an
  operator changed a `model:` value. Any future `EgressPolicy` implementation should honor this
  same convention rather than inventing a per-implementation provider-identity scheme.
- `EgressDecision` is deliberately content-free (`allowed`, `reason`, `classification`,
  `provider`, `operation` — no free-text beyond a bounded `reason` string built only from those
  same fields). Any future field added to this type must preserve that property; it is audited
  and logged on the assumption that it never carries caller content.
- This contract does not define, and must not be read to imply, any L0/L1/L2 assurance-level
  claim (ADR-0015 §3) or conformance-report field. That remains explicitly Lot 21 scope, gated on
  its own accepted contract ADR — this ADR neither pre-approves nor forecloses what Lot 21 does
  with egress evidence.

## Relationship to prior decisions

- **ADR-0015** (accepted): §5 already states "data protection is part of assurance" and names
  Lot 20 as the first dependency before Lots 21–22 proceed. This ADR is the outbound-data-boundary
  decision ADR-0015 itself deferred to Lot 20 — it does not revise ADR-0015's own scope.
- **ADR-0007** (accepted, layer boundaries): `EgressPolicy` follows the same optional-role,
  `Container`-registered pattern as `TenantPolicy`/`Redactor` — no new layering exception was
  introduced. `orchestration/registry.py`'s manifest-coverage validation reads the raw
  `governance.egress_policy.config` dict rather than constructing `ManifestEgressPolicy`,
  preserving the rule that `orchestration/` may import only `core/`+`contracts/`+`orchestration/`,
  never `security/`.
- **Lot 21** (planned): explicitly gated on this ADR's disposition (accept/revise/reject) plus its
  own focused contract ADR, per `docs/refactoring-plan.md`.

## Consequences

### Positive

- Closes a real, previously undefended path (raw query/chunk/document content reaching a remote
  provider before any classification-aware decision) for every owned embedder/generator/reranker
  call and the LangGraph delegated-engine handoff, when an operator opts in.
- Local-only deployments remain fully unaffected and require no new configuration.
- Provider identity is manifest data, not vendor-specific code — no OpenAI/Anthropic/LangGraph
  semantics were hardcoded into `contracts/` or `core/`, per CLAUDE.md §07.

### Negative / risks

- **The opt-in design (§2) means the acceptance criterion "no owned external path can receive
  classified content unless the manifest explicitly permits it" is only true for a pipeline that
  configures `governance.egress_policy`.** An unconfigured pipeline wiring a remote provider has
  no protection from this contract at all — accepted explicitly, not an oversight (§2).
- Query-time content is never individually classified (§3) — a deployment whose query text itself
  may be sensitive, using a remote embedder, relies entirely on `default_classification`, not a
  per-query decision.
- No pseudonymization means an allowed call is still a real disclosure of unmodified content to
  whatever provider the manifest names — this contract decides *whether* a call happens, not what
  it contains.

## Open decision

**This ADR's own Status (Proposed) is itself the primary open decision** — accept, revise, or
reject is Herbert Gourout's to make. Revision candidates, if not accepted as-is, most likely
concern §2 (the opt-in-vs-default-closed boundary) — see `.review/handoff.md` for the exact
finding this responds to and the reasoning already exchanged.
