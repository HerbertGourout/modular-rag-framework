# Lot 7 — Engine-Neutral Contracts and Compatibility Policy

**Status:** COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 4 (characterization), Lot 6 (LangGraph selected, ADR-0006 accepted)

## What was done

- **`src/modular_rag/contracts/engine.py`** — the `DocumentEngine` Protocol and its supporting
  types: `EngineCapability` (declared, not probed, capability set), `ExecutionContext`
  (tenant/correlation/request identity, `CancellationToken`, `GovernanceHook`, extension
  envelope), `EngineRequest`/`EngineResult`/`EngineStep` (normalized, versioned via a
  `schema_version` field, `EngineStep` deliberately shape-compatible with
  `core.models.trace.TraceStep` so an engine's execution maps onto the owned audit trail
  without the engine knowing our types), `GovernanceDecision`/`GovernanceHook` (a minimal
  locally-defined Protocol — deliberately not importing `contracts.security.SecurityGuard`, so
  `engine.py` has no inter-contract dependency).
- **`core/errors.py`**: `EngineError`, `EngineTimeoutError`, `EngineCancelledError`,
  `EngineCapabilityError` — added to the existing flat error hierarchy, not a new per-module
  error file, matching the codebase's established convention.
- **`contracts/__init__.py`**: all new types exported, per `.claude/rules/contracts.md`'s "a new
  contract file requires an entry in `contracts/__init__.py`" rule.
- **`tests/contract/fakes/document_engine.py`**: `FakeDocumentEngine` — a real (not mocked)
  in-memory implementation of the Protocol, covering the same route → retrieve → governance
  guard → generate shape the Lot 6 spikes used, so the conformance suite tests actual behavior.
- **`tests/contract/test_engine_conformance.py`**: 11 semantic conformance tests — not just
  `isinstance()`. Covers: capability-gated methods raising `EngineCapabilityError` when the
  declared capability is absent (`astream`), a governance hook provably stopping `generate` from
  running (not just "was called"), a governance hook being *ignored* (not silently honored) when
  `GOVERNANCE_INTERCEPT` isn't declared, cancellation raising `EngineCancelledError` when
  declared and being silently ignored when not, and `arun`/`run` producing equivalent results.
- **`docs/architecture/document-engine-contract.md`**: the compatibility/deprecation policy —
  what's safe to add without a new ADR (capability values, optional fields, extension-envelope
  keys) vs. what requires one (Protocol method signature changes, `capabilities` return-type
  changes, required-field changes), plus a deprecation window rule once a second adapter exists
  (Lot 15).

## Design decisions worth recording

- **No vendor types anywhere in `contracts/engine.py`.** Not even in a comment example — the
  whole point of Lot 7 is that Lot 8 (native) and Lot 15 (LangGraph) adapters are the *only*
  places a vendor type may exist. Verified by construction: the module imports only from
  `core.models` and the stdlib.
- **Governance interception modeled as a local Protocol, not a cross-contract import.**
  `GovernanceHook` is structurally compatible with adapting a real `SecurityGuard` (Lot 11c) but
  `engine.py` doesn't depend on `contracts.security` — keeps the port genuinely minimal and
  avoids giving `contracts/` internal coupling it doesn't have today.
- **`schema_version` on request/result, not a version on the Protocol itself.** Lets the data
  shape evolve independently of the method signatures — documented in the compatibility policy
  as the intentional versioning seam.
- **Cancellation semantics don't overclaim.** The compatibility doc explicitly repeats the Lot 6
  spike's caveat: a cancelled token stops the *caller* promptly, but whether underlying
  blocking work is actually killed is an adapter-level concern this contract can't guarantee.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 261 tests total (202 unit + 59 contract, up from 250) — the +11 are all in the new conformance
  suite; no existing test touched.
- mypy baseline unchanged at 35 — the new fully-typed module introduced zero new errors.

## Lot 7 acceptance (per `docs/refactoring-plan.md` §6)

"Vendor-neutral types; semantic fake/conformance tests; versioning policy" — all three
delivered: `contracts/engine.py` has no vendor types, `test_engine_conformance.py` tests
behavior not just structure, `docs/architecture/document-engine-contract.md` is the versioning
policy.

## Next

Lot 8 (native `RAGEngine` adapter behind this port, removing the private-`_c`-container access
found in Lot 4) and Lot 9 (versioned manifests) both depend on Lot 7 and can now proceed.
