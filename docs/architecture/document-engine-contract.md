# The `DocumentEngine` Contract — Compatibility and Deprecation Policy

**Source:** [`src/modular_rag/contracts/engine.py`](../../src/modular_rag/contracts/engine.py)
**Governing decisions:** [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2
(what's delegated), [ADR-0006](../adr/0006-external-engine-selection.md) (LangGraph selected)
**Established:** Lot 7, `docs/refactoring-plan.md`

## What this contract is for

`DocumentEngine` is the one place vendor types are allowed to leak in — and only inside an
adapter's implementation, never in this Protocol's own signatures. Everything on either side of
it (the control plane calling in; an adapter like the shipped LangGraph one,
`adapters/llms/langgraph_engine.py`'s `LangGraphEngineAdapter`, implementing it) talks in the
neutral types below, never in the external engine's own API shapes.

## Versioning

- **`CONTRACT_VERSION`** (currently `"1.0"`, in `contracts/engine.py`) versions the *shape* of
  `EngineRequest`/`EngineResult`, carried as each instance's own `schema_version` field — not
  the Python `Protocol` itself. This lets a request/result schema evolve (e.g. a v2 adds a
  field) while the `DocumentEngine` Protocol's method signatures stay stable, and lets a caller
  or adapter detect which schema version it's holding without needing a full type-system
  migration.
- **The `DocumentEngine` Protocol's method signatures** (`run`, `arun`, `astream`, `capabilities`,
  `name`, `engine_version`) are versioned by this document, not a field. A breaking change to
  any of them (removing a method, changing a required parameter, narrowing a return type)
  requires a new ADR, per this project's contract-change rule
  (`.claude/rules/contracts.md`: *"Tout changement qui affecte le layering nécessite un nouvel
  ADR"*), and must update every conformance test in
  `tests/contract/test_engine_conformance.py` in the same change.
- **`EngineCapability`** is additive-safe: adding a new capability value is not breaking (old
  adapters simply never declare it, so `capability in engine.capabilities` checks stay
  correct). Removing or renaming an existing value IS breaking — every adapter and every caller
  that checks for it needs a coordinated update.

## What's safe to add without a new ADR

- A new `EngineCapability` value.
- A new optional field on `EngineRequest`, `EngineResult`, `EngineStep`, or `ExecutionContext`
  (dataclasses here are not `frozen` against *new* optional fields with defaults — adding one
  doesn't break existing callers who don't set it).
- A new key inside `ExecutionContext.extensions` or `EngineRequest.extensions` — that's exactly
  what the extension envelope is for: adapter- or deployment-specific data that doesn't belong
  in the neutral contract but also shouldn't require a contract change to pass through. Nothing
  in `contracts/engine.py` may ever read its own contents; only a specific adapter may.

## What requires a new ADR

- Adding, removing, or changing the signature of a `DocumentEngine` method.
- Changing what `capabilities` returns (e.g. making it a `list` instead of a `frozenset`).
- Removing a field from `EngineRequest`/`EngineResult`/`EngineStep`/`ExecutionContext`, or
  making an optional field required.
- Bumping `CONTRACT_VERSION` to `"2.0"` for a genuinely breaking request/result shape change.

## Deprecation window

A second adapter now exists (Lot 15's LangGraph adapter, alongside Lot 8's native one) — any
contract change must keep both green through `tests/contract/test_engine_conformance.py` for at
least one full lot cycle before an old field/capability is removed — this is the same "add
before move" principle the rest of the programme follows
(`docs/refactoring-plan.md` §8, item 2). `test_engine_conformance.py` parameterizes over both
`NativeEngineAdapter` and `LangGraphEngineAdapter` (plus a minimal fake in
`tests/contract/fakes/document_engine.py` used to test the port's own semantics in isolation from
either real adapter) against the identical conformance suite.

## Extension-envelope discipline

`extensions: dict[str, Any]` exists on both `ExecutionContext` and `EngineRequest` specifically
so adapter-specific or deployment-specific data has somewhere to go that isn't the neutral
contract itself. Rules for using it:

1. Never branch core control-plane logic (governance, audit, quality) on the *contents* of
   `extensions` — if a value needs to influence owned-capability behavior, it belongs in the
   typed contract, not the envelope.
2. An adapter may read and write its own namespaced keys (e.g. `extensions["langgraph"]`) but
   must not require the caller to populate them for the adapter to function at its declared
   capability level.
3. Nothing under `extensions` is covered by this compatibility policy — an adapter may change
   what it stores there at will, since by definition nothing outside that adapter should depend
   on it.

## Governance interception, concretely

`GovernanceHook` is intentionally a minimal, locally-defined Protocol in `contracts/engine.py`
rather than a direct dependency on `contracts.security.SecurityGuard` — `engine.py` must not
import from another contract module for a capability this specific. The semantic conformance
suite proves the *contract* is enforceable (a blocking hook stops `generate` from running, and is
correctly ignored by an engine that doesn't declare `EngineCapability.GOVERNANCE_INTERCEPT`).

Beyond the contract-level proof, `LangGraphEngineAdapter`'s `_node_guard()` now wires this for
real: it reads `state["context"].governance_hook`, and — only when the adapter declares
`GOVERNANCE_INTERCEPT` and a hook is actually present — calls `hook.check("generate", {"query":
...})`, blocking the run on a `decision.allowed=False` exactly as the conformance suite requires.

This sits *alongside*, not instead of, that same node's direct `Container.guard.check_query()`
call. The adapter's own inline comment is explicit about the distinction: the direct guard call
must behave identically to `RAGEngine`/`NativeEngineAdapter`'s own `SecurityError` convention, an
adapter-specific parity requirement from Lot 15; the port-level `GovernanceHook` is the separate,
generic mechanism any `DocumentEngine` caller can rely on regardless of which adapter is selected.

`NativeEngineAdapter` has no `GovernanceHook`-equivalent wiring to stay parallel with — its own
governance path is `RAGEngine`'s direct calls into `Container.guard`/`policy_engine`/
`tenant_policy`, which predate the `DocumentEngine` port entirely.

## Cancellation, concretely

`CancellationToken` is a plain mutable object, not a dataclass — cancellation is inherently
cross-task shared state, which frozen/dataclass semantics don't fit. An adapter that declares
`EngineCapability.CANCELLATION` must check `context.cancellation_token.is_cancelled` at every
reasonable step boundary and raise `EngineCancelledError` promptly; the Lot 6 spike evidence
(`docs/refactoring/lot-6-spike/README.md`) already flagged that for a sync-blocking underlying
call, "promptly" may only mean the *caller* stops waiting, not that the underlying work is
actually killed — that distinction is an adapter-level resource-cleanup concern, not something
this contract can guarantee on the engine's behalf.
