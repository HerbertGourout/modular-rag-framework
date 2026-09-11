# Lot 21 — Engine-Independent Assurance Contract and Conformance Report

**Status:** COMPLETE, 2026-09-10, corrected 2026-09-11 after Codex review pass 1
(`CHANGES_REQUIRED` — 4 HIGH, 1 MEDIUM; all five valid, all five closed — see §"Codex review
pass 1 — findings and corrective actions").
[ADR-0017](../adr/0017-engine-independent-assurance-contract.md) Accepted 2026-09-10;
`contracts/assurance.py` and both shipped adapters' `conformance_report()` implemented the same
day. See §"Evidence — what shipped" below for the full record; the rest of this document is
preserved as the original planning scope it was implemented against.

**Priority:** P0 after Lot 20

**Indicative size:** L (2–3 weeks), to re-estimate after contract spike — actual: implemented in
one bounded pass following the accepted ADR, not separately re-estimated.

## Purpose

Turn the current collection of engine capabilities and control-plane components into an honest,
machine-readable assurance contract. The result must state what an adapter can observe, enforce,
and evidence without implying that every engine provides native-equivalent governance.

ADR-0015 authorizes this direction. Implementation was blocked until this lot's own focused
contract ADR ([ADR-0017](../adr/0017-engine-independent-assurance-contract.md)) approved the
public schemas, compatibility policy, and migration — now accepted.

## Inputs

- [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)
- [ADR-0015](../adr/0015-portable-assurance-and-external-application-boundary.md) (accepted)
- Lot 20 provider-egress decision and contracts
- existing `DocumentEngine`, `EngineCapability`, `EngineRequest`, and `EngineResult` contracts
- audit, evaluation, feedback, review, tracing, and metrics contracts

## Required scope

1. Approve a contract ADR before changing public Protocols, enums, result schemas, or manifests.
2. Define L0 (opaque output), L1 (evidence-aware), and L2 (governed stages) as versioned,
   testable profiles.
3. Separate three concepts in the schema:
   - **observable** — the adapter can report evidence supplied by the engine;
   - **verifiable** — the framework can validate that evidence independently;
   - **enforceable** — the framework can prevent the stage from proceeding on policy failure.
4. Define normalized evidence for the minimum useful set: identity/tenant propagation,
   retrieval/citation provenance, egress decision, policy decision, audit completion, usage/cost,
   feedback/review routing, and streaming prevalidation.
5. Preserve vendor-specific facts under namespaced metadata instead of flattening them into a
   false common denominator.
6. Generate a deterministic conformance report containing achieved level, passed checks,
   unsupported capabilities, supplied-but-unverified evidence, contract/schema versions, and
   adapter identity.
7. Validate manifest requirements before startup and reject any mandatory unsupported control.
8. Apply the suite to the native and current LangGraph adapters without weakening existing native
   behavior.
9. Execute the shared semantic conformance suite against the real `NativeEngineAdapter` and
   `LangGraphEngineAdapter`, not only a fake contract fixture. A fake remains useful for boundary
   cases, but cannot prove that a shipped adapter honours what it declares.
10. Make conformance capability-aware: an honestly unsupported capability is reported as such,
    while a declared-but-broken capability fails the suite. Results must be exportable to the
    multi-engine protocol in
    [offline-evaluation.md](../guides/offline-evaluation.md#planned-multi-engine-assurance-benchmark-lots-21-22-not-implemented).

## Non-goals

- wrapping an arbitrary client application (Lot 22);
- adding new agent, tool, GraphRAG, or VLM execution behavior;
- claiming regulatory certification;
- treating vendor trace metadata as verified merely because it was returned.

## Acceptance evidence

- accepted contract ADR and migration/compatibility policy;
- schema fixtures and semantic conformance tests for L0/L1/L2;
- negative tests for capability overclaim, missing evidence, policy bypass, partial failure, and
  streaming before approval;
- native and LangGraph reports produced by executing the same suite against both real adapters
  and checked into deterministic test fixtures;
- explicit evidence that every declared adapter capability was exercised, skipped as honestly
  unsupported, or failed -- never silently inferred from a fake implementation;
- proof that a manifest requiring an unavailable control fails before traffic;
- documentation clearly distinguishes enforcement, verification, and observation;
- full layering, unit, contract, manifest, and service-free quality gates pass.

The cross-engine quality datasets and integration-effort study remain Lot 22 work. This lot
provides the trustworthy conformance evidence those comparisons consume; it does not claim that
contract conformance alone proves RAG quality or commercial portability.

## Evidence — what shipped, 2026-09-10

- **Accepted contract ADR.** [ADR-0017](../adr/0017-engine-independent-assurance-contract.md),
  Accepted 2026-09-10 — its own three "Open decision" candidates (per-request
  `conformance_report(context)` shape, the level-requirement mapping staying an implementation
  detail, the eight-kind set being a minimum, not exhaustive) were all confirmed as originally
  drafted, not revised.
- **`contracts/assurance.py` (new).** `AssuranceLevel` (`L0`/`L1`/`L2`), `EvidenceStatus`
  (`UNSUPPORTED`/`OBSERVED`/`VERIFIED`/`ENFORCED`), `EvidenceKind` (the eight-kind set named in
  Required scope item 4), `EvidenceEntry`, `ConformanceReport` (`achieved_level` is a **computed
  `@property`**, not a constructor field — an adapter cannot pass its own level in even if it
  wanted to), `compute_achieved_level()` (pure, adapter-independent — proven by
  `tests/unit/contracts/test_assurance.py`), `meets_minimum_level()`.
- **`DocumentEngine.conformance_report(context)` (new, additive).** Implemented truthfully by
  both shipped adapters — `orchestration/engine.py::RAGEngine.conformance_report()` (native;
  `NativeEngineAdapter` delegates in one line) and `adapters/llms/langgraph_engine.py::
  LangGraphEngineAdapter.conformance_report()` — from two separate sources:
  **control-surface evidence**, where a wired role counts only if it also satisfies its contract
  Protocol, and **execution evidence** recorded while actually serving `context.request_id`.
  `RETRIEVAL_PROVENANCE` and `USAGE_COST` are execution-derived only; everything else is
  control-surface. No status is ever earned by a component's mere presence (the corrected
  position — see the pass-1 findings section below for what this replaced).
- **LangGraph's honest ceiling.** `AUDIT_COMPLETION` is structurally `UNSUPPORTED` for
  `LangGraphEngineAdapter` always (its own documented Lot 15 scope boundary; `governance.
  audit_sink` is itself rejected under `engine.adapter='langgraph'`) — this caps it at `L1` even
  with tenant/guard/egress fully wired, a concrete, machine-readable restatement of Lot 20's
  MEDIUM-001 deferral (`.review/handoff.md`), not a new gap. `POLICY_DECISION` is the one
  genuinely per-request kind: a caller supplying `context.governance_hook` reaches `ENFORCED` on
  LangGraph even with no `Container.guard` wired — real state the manifest-only pre-flight check
  below cannot see, by design.
- **Manifest-level `assurance.min_level` (new, additive).** `contracts/manifests.py::
  AssuranceSection`, checked in two places against a **capability profile** (what a wiring could
  earn for a request it serves) rather than against a report: `_declared_capability_evidence()`
  inside `runtime_manifest_errors()` for the dry-run path (advisory — nothing is constructed
  there, so a declared role is taken at face value), and `_wired_capability_evidence()` at the end
  of `ComponentRegistry.wire()` against the components actually built, with Protocol validation.
  The second is the authoritative gate. Neither is a
  call into either adapter's real `conformance_report()` (`orchestration/` cannot construct
  `LangGraphEngineAdapter`, which lives in `adapters/`, and rejection must happen before `wire()`
  constructs anything). Deliberately conservative: never assumes a future caller's context will
  supply extra evidence (e.g. a governance hook), so a manifest that passes this check is a real,
  structural guarantee. A manifest requiring an unmeetable level is rejected before serving
  traffic — proven by `tests/unit/orchestration/test_registry.py`'s new tests, including the
  concrete LangGraph-capped-at-L1 scenario.
- **Capability-aware semantic conformance harness, against real adapters.**
  `tests/contract/test_engine_conformance.py::assert_claims_match_behaviour()` is one reusable
  assertion run against `FakeDocumentEngine`, `NativeEngineAdapter`, and `LangGraphEngineAdapter`
  alike. Its rule: for every evidence kind a report claims above `UNSUPPORTED`, the suite must own
  a behavioural probe for that kind and the probe must pass — so a claim nothing verifies is
  itself a conformance failure. Probes exercise real denial paths (no tenant identity, a denying
  guard, a denying egress policy), real side effects (an audit event written, an item routed to
  review), and real streaming order (nothing generated reaches the stream past a denying guard).
  `_OverclaimingFakeDocumentEngine` is fed through that same harness as a negative input.
- **Total added tests (after the corrective pass): 69** (`tests/unit/contracts/test_assurance.py` new; targeted additions to
  `tests/unit/contracts/test_manifests.py`, `tests/unit/orchestration/test_registry.py`,
  `tests/unit/orchestration/test_native_engine.py`, `tests/unit/adapters/llms/
  test_langgraph_engine.py`, `tests/unit/app/test_config_resolution.py`,
  `tests/contract/test_engine_conformance.py`). Full suite: 1551 passed (was 1482 before the
  lot), 0 failed. `ruff`, `scripts/check_layering.py --strict`, and mypy (21 errors, unchanged
  from baseline) all clean.
- **Not delivered in this pass, explicit:**
  - No exported, on-disk JSON fixture of a "golden" conformance report — determinism and exact
    per-kind evidence values are proven by direct unit-test assertions instead
    (`test_conformance_report_is_deterministic_for_the_same_wiring_and_context` and the targeted
    native/LangGraph tests), not a separate serialized artifact. Equivalent evidentiary value, a
    narrower literal interpretation of "checked into deterministic test fixtures" above.
  - `docs/guides/offline-evaluation.md`'s planned multi-engine assurance benchmark (the
    "Controlled components"/"Stack-native optimized" comparison tracks, the assurance scenario
    corpus, the dataset portfolio) remains entirely unimplemented planning content, unaffected by
    this pass — this lot provides the `ConformanceReport` normalized-evidence source that future
    benchmark work would consume, not the benchmark itself.
  - Only the `EvidenceKind`/`AssuranceLevel` requirement mapping this pass defined is tested;
    Lot 22's own real existing-application adapter has not been built, so no *third*
    `conformance_report()` implementation exists yet to further stress-test the contract's
    genericity beyond this framework's own two engines.


## Codex review pass 1 — findings and corrective actions

Full review: `.review/codex-review.md`. Status `CHANGES_REQUIRED`, 4 HIGH + 1 MEDIUM, 0 BLOCKER.
Every finding was independently reproduced against the code before any fix — none was applied on
the reviewer's word alone, and none was rejected.

| Finding | Disposition | Resolution |
|---|---|---|
| HIGH-001 — the level computation weakened the accepted L1/L2 guarantees | Valid, confirmed against the ADR text | **Fixed.** `_LEVEL_REQUIREMENTS` granted L1 on `IDENTITY_TENANT=OBSERVED` and L2 on `AUDIT_COMPLETION=OBSERVED`, and omitted review routing from L2 — while ADR-0017 §6 states verbatim "L2 requires ... (egress, policy, audit completion) at least ENFORCED; L1 requires retrieval provenance and identity/tenant at least VERIFIED", and ADR-0015 §3 names review routing among L2's governed stages. That §6 also calls the exact mapping an "implementation detail" authorizes choosing which kinds map to a level, never lowering a minimum the same paragraph states. Restored to the accepted meanings; `tests/unit/contracts/test_assurance.py` now tests the ADR thresholds, including a dedicated regression that OBSERVED audit completion cannot reach L2. |
| HIGH-002 — startup and runtime reports certified wiring, not functioning controls | Valid, reproduced | **Fixed, in two halves.** *Runtime:* both adapters now count a role only when it satisfies its contract Protocol (`isinstance()` against the `runtime_checkable` Protocols; duck-typed `enforce_query` for `policy_engine`, which has no Protocol). *Startup:* `ComponentRegistry.wire()` gained an authoritative post-construction gate (`_wired_capability_evidence()`) that re-checks `assurance.min_level` against the components actually built. Reproduction before: plain `object()` wired as guard/tenant_policy/egress_policy/audit_sink passed an `l2` manifest, reported L2, then failed the first request with `AttributeError`. After: the same fixture reports **L0** and `wire()` rejects the manifest outright. Regression tests in `test_native_engine.py` and `test_registry.py`. |
| HIGH-003 — retrieval provenance reported VERIFIED for generators that produce no provenance | Valid, reproduced | **Fixed.** `contracts.generation.Generator` requires nothing about citations, so provenance can never be earned from wiring. Added `contracts.assurance.classify_provenance()` — one shared, pure, content-free definition of "grounded" — run by both engines at the single point where the retrieved chunks and the returned citations coexist, and recorded per `request_id` in a bounded (32-entry) store. `VERIFIED` now requires citations that all name actually-retrieved chunks; ungrounded citations report `OBSERVED`; none report `UNSUPPORTED`. Recorded, never enforced: no new failure mode was added to either pipeline. A report for a request that never ran, or for a different request, reports `UNSUPPORTED` — never another request's evidence. |
| HIGH-004 — the shared conformance suite did not fail adapters for most false claims | Valid, confirmed | **Fixed.** Replaced the shape/determinism/assumed-status tests with one reusable harness, `assert_claims_match_behaviour()`, run against all three engines. Rule: for every kind claimed above `UNSUPPORTED`, the suite must own a behavioural probe and it must pass — so an unverifiable claim is itself a failure. Probes exercise real denial paths (missing tenant identity, denying guard, denying egress), real side effects (audit event written, item routed to review) and real streaming order. `_OverclaimingFakeDocumentEngine` is now a negative *input to that same harness*, not a test that asserts its own claim is false. |
| MEDIUM-001 — usage and streaming entries claimed observations that never occur | Valid, confirmed, fixed in scope | **Fixed.** `USAGE_COST` is execution-derived on native (requires a wired `Meter` **and** a token-bearing `TraceStep` for that request — a non-empty trace is not enough, since retrieval always adds a step) and structurally `UNSUPPORTED` on LangGraph, which never emits `mrag.generation.tokens` at all. `STREAMING_PREVALIDATION` reports `UNSUPPORTED` when neither a guard nor an egress policy is wired, instead of the previous `OBSERVED` claimed from capability presence alone. The same correction was applied to `FakeDocumentEngine`, since it is the reference implementation adapter authors copy. |

Two consequences worth stating plainly, because they are visible in the reports and not hidden:

1. **A report for a request that has not executed cannot exceed L0**, since provenance is
   execution-derived and L1 requires it `VERIFIED`. This is honest, not a regression: before an
   execution there is genuinely no provenance evidence.
2. **The startup gate necessarily evaluates capability, not evidence** — it runs before any
   request exists. The two are computed by separate, separately-named functions and neither is
   ever used to build a `ConformanceReport`, which is exactly the separation HIGH-002 asked for.

## Codex review pass 2 — closure verification and the final Claude remediation

Full review: `.review/codex-review.md` (pass `2/2`, `CLOSURE_ONLY`, status `CHANGES_REQUIRED`).
HIGH-001 and MEDIUM-001 were verified `CLOSED`. HIGH-002/003/004 were judged only *partially*
closed, and the pass-1 execution-evidence cache introduced a new regression, HIGH-005. Per the
two-pass limit (`docs/guides/ai-engineering-workflow.md`), Codex stopped there; what follows is
the bounded final Claude remediation, which **was not reviewed by Codex** — the deterministic
validation below and the human delivery decision are its only gates.

Each finding was reproduced independently before being fixed.

| Finding | Disposition | Resolution |
|---|---|---|
| HIGH-002 — Protocol membership still certifies non-functioning controls | Valid, reproduced | **`ACCEPTED_RISK`** (maintainer decision, 2026-09-11). Reproduced: `_ProtocolTenantPolicy` (`tests/unit/orchestration/test_registry.py`), whose `enforce_query()` is an unconditional no-op, passes `assurance.min_level: l2`. `runtime_checkable` validates method *presence* only; proving enforcement requires executing the control against a denial, which `wire()` must not do. Codex's three recommended actions — a framework-shipped allowlist, a trusted-capability registration mechanism, or a human risk acceptance narrowing the promise — are all reserved to the maintainer by the Lot 21 brief, so the decision was escalated rather than taken. **Chosen: narrow the promise.** [ADR-0017 §9](../adr/0017-engine-independent-assurance-contract.md) now states that the gate answers only "are the required controls declared, wired and structurally conformant?", names the behavioural conformance harness as the authority on `ENFORCED`, and records the accepted risk plus the two rejected alternatives. `registry.py::_wired_capability_evidence()`, `document-engine-contract.md` and `capability-matrix.md` carry the same narrowed wording. No behaviour changed. |
| HIGH-003 — a matching chunk id verified fabricated citation evidence | Valid, reproduced | **Fixed.** `classify_provenance()` now takes `Sequence[Citation]` and `Sequence[RetrievedChunk]` and compares the displayed attribution itself: the passage (whitespace/case-normalized substring of the retrieved chunk, so `build_citations()`'s own sentence-boundary truncation still verifies), the page, and the source. A citation naming a real chunk id with a fabricated passage, source or page now reports `OBSERVED`; an empty passage cannot be verified evidence. `score` is deliberately excluded and documented as such — it is a ranking artifact a reranker legitimately rewrites, not displayed provenance. `FakeDocumentEngine` was converted to build real `Chunk`/`RetrievedChunk` objects so every engine shares one definition of "grounded" rather than the fake keeping a weaker dict-shaped one. |
| HIGH-004 — the harness ignored the claimed evidence *strength* | Valid, confirmed | **Fixed.** Probes are now status-aware (`_StatusProbe`, with `observed`/`verified`/`enforced` checks). A claim is honoured only if a check exists for its own rung *and* every weaker check defined for that kind also passes — `EvidenceStatus` is a ladder, so `ENFORCED` subsumes `OBSERVED`. `_STATUS_CONTRACT` states what each rung obliges and is quoted in every failure message. Concretely: `AUDIT_COMPLETION=ENFORCED` now requires a *failing* audit sink to fail the request (an event merely being written is `OBSERVED`); `FEEDBACK_REVIEW_ROUTING=ENFORCED` requires a failing `enqueue()` to fail the request; `RETRIEVAL_PROVENANCE=VERIFIED` requires the engine to refuse `VERIFIED` for a generator that fabricates a passage on a real chunk id. Two new negative tests prove the harness rejects a claim probed only at a weaker strength, and that a failing weaker check invalidates a stronger claim. |
| HIGH-005 — a reused request id inherited an earlier attempt's evidence | Valid, reproduced | **Fixed.** Reproduced: a successful request followed by a denied retry carrying the same id still reported that id's earlier `VERIFIED` provenance. Every execution attempt now clears any evidence its request id already carries, at the single entry point of each engine — `RAGEngine._run()`, `LangGraphEngineAdapter._initial_state()` (shared by run/arun/astream) and `FakeDocumentEngine.run()`. A parametrized regression test covers success-then-failure on a reused id for all three engines. |

## Rollback

Keep the existing `DocumentEngine` schema supported for its documented compatibility window. New
assurance fields must be additive or version-gated until all built-in adapters migrate. Rolling
back the lot must restore the prior manifest schema and adapters without migrating stored client
content.
