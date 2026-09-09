# Lot 21 — Engine-Independent Assurance Contract and Conformance Report

**Status:** PLANNED — Lot 20 is complete ([ADR-0016](../adr/0016-provider-egress-control.md)
Accepted 2026-09-09). This lot's own contract ADR,
[ADR-0017](../adr/0017-engine-independent-assurance-contract.md), is drafted (Proposed,
2026-09-09) but not yet accepted — implementation is still blocked until it is.

**Priority:** P0 after Lot 20

**Indicative size:** L (2–3 weeks), to re-estimate after contract spike

## Purpose

Turn the current collection of engine capabilities and control-plane components into an honest,
machine-readable assurance contract. The result must state what an adapter can observe, enforce,
and evidence without implying that every engine provides native-equivalent governance.

ADR-0015 authorizes this direction. Implementation remains blocked until this lot's own focused
contract ADR ([ADR-0017](../adr/0017-engine-independent-assurance-contract.md)) approves the
public schemas, compatibility policy, and migration.

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
- native and LangGraph reports checked into test fixtures;
- proof that a manifest requiring an unavailable control fails before traffic;
- documentation clearly distinguishes enforcement, verification, and observation;
- full layering, unit, contract, manifest, and service-free quality gates pass.

## Rollback

Keep the existing `DocumentEngine` schema supported for its documented compatibility window. New
assurance fields must be additive or version-gated until all built-in adapters migrate. Rolling
back the lot must restore the prior manifest schema and adapters without migrating stored client
content.
