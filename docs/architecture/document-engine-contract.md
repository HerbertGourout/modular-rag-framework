# The `DocumentEngine` Contract — Compatibility and Deprecation Policy

**Source:** [`src/modular_rag/contracts/engine.py`](../../src/modular_rag/contracts/engine.py)
**Governing decisions:** [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2
(what's delegated), [ADR-0006](../adr/0006-external-engine-selection.md) (LangGraph selected),
[ADR-0017](../adr/0017-engine-independent-assurance-contract.md) (Lot 21, assurance/conformance)
**Established:** Lot 7, `docs/refactoring-plan.md`

> **Current limit:** this contract normalizes execution, results, steps, errors, generic
> capabilities, and — since Lot 21 — a machine-readable, per-request assurance report
> (`conformance_report()`, see below). It is still not a regulatory certification, and the current
> LangGraph adapter still builds a fixed graph rather than wrapping an existing client
> application: that remains Lot 22, planned but not implemented — nothing in this document should
> be read as if that part of ADR-0015 already shipped.

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

## Assurance evolution — implemented (Lot 21, ADR-0017 Accepted 2026-09-10)

`contracts/assurance.py` (new) defines the versioned assurance schema ADR-0015 §4 called for:
`AssuranceLevel` (`L0`/`L1`/`L2`, matching ADR-0015 §3's table exactly — this module does not
redefine what the levels mean, only how an adapter proves which one it achieves),
`EvidenceStatus` (`UNSUPPORTED`/`OBSERVED`/`VERIFIED`/`ENFORCED` — keeping "the adapter says so"
strictly distinct from "the framework's own code independently checked/can block it"),
`EvidenceKind` (the eight-kind minimum-useful-set ADR-0017 §4 names: identity/tenant, retrieval
provenance, egress decision, policy decision, audit completion, usage/cost, feedback/review
routing, streaming prevalidation), and `ConformanceReport` — whose `achieved_level` is a
**computed `@property`**, not a constructor parameter, so no adapter can assert its own level;
`compute_achieved_level()` is the sole, pure, adapter-independent function that ever produces one.

`DocumentEngine` gained exactly one additive method for this, per the "what requires a new ADR"
rule above — ADR-0017 is that ADR:

```python
def conformance_report(self, context: ExecutionContext) -> ConformanceReport: ...
```

Both shipped adapters implement it truthfully from their own actually-wired `Container` roles and
what they recorded while serving the request —
`orchestration/engine.py::RAGEngine.conformance_report()` (delegated to by `NativeEngineAdapter`)
and `adapters/llms/langgraph_engine.py::LangGraphEngineAdapter.conformance_report()`. The two
reports are **not** required to agree: LangGraph's own documented Lot 15 scope boundary (it never
reaches `RAGEngine._audit()`, and `governance.audit_sink` is itself rejected under
`engine.adapter='langgraph'`) makes `AUDIT_COMPLETION` structurally `UNSUPPORTED` for that
adapter always — which caps it below `L2` even with tenant/guard/egress all wired, honestly,
rather than manufacturing native-equivalent parity it cannot back.

`tests/contract/test_engine_conformance.py` owns the shared, capability-aware harness
(`assert_claims_match_behaviour()`), run against `FakeDocumentEngine`, `NativeEngineAdapter`, and
`LangGraphEngineAdapter` alike. Its rule: **for every evidence kind a report claims above
`UNSUPPORTED`, the suite must own a behavioural probe, and that probe must pass** — so a claim
nothing can verify is itself a conformance failure, and an adapter cannot quietly add one. An
honestly `UNSUPPORTED` kind is skipped, never punished. `_OverclaimingFakeDocumentEngine` is fed
through that same harness as a negative input, proving it rejects a false claim rather than
asserting the claim is false by hand.

### Evidence vs capability — two deliberately separate things

A `ConformanceReport` answers "what was true for **this request**". Two of its kinds can only be
earned by an execution, never by configuration:

- `RETRIEVAL_PROVENANCE` is `VERIFIED` only when the framework's own grounding check
  (`contracts.assurance.classify_provenance()`, shared by both engines) confirmed that every
  citation the generator returned names a chunk that was actually retrieved for that request.
  `contracts.generation.Generator` requires nothing about citations at all, so a custom or
  defective generator returning none — or returning unrelated ones — must never yield a
  provenance claim. Citations present but ungrounded report `OBSERVED`; none at all report
  `UNSUPPORTED`.
- `USAGE_COST` is `OBSERVED` only when a `Meter` is wired **and** the generator actually produced
  a token-bearing `TraceStep` for that request. LangGraph reports it `UNSUPPORTED` always:
  `mrag.generation.tokens` is emitted only inside `RAGEngine`, which that adapter never calls.

Every other kind is control-surface evidence, and a wired role counts only when it also satisfies
its contract Protocol — a plain `object()` registered as `tenant_policy` is not a tenant policy.
`isinstance()` against a `runtime_checkable` Protocol is the same pure structural check
`registry.wire()` already applies to `VectorIndexer` (ADR-0009).

An optional manifest field, `assurance.min_level`, lets a manifest require a minimum level before
serving traffic. Because a startup gate by definition has no execution evidence, it is checked
against a **capability profile** — "what could this wiring earn for a request it serves" — which
is computed by two clearly separate functions in `orchestration/registry.py`, never by calling an
adapter's `conformance_report()`:

- `_declared_capability_evidence()` runs inside `runtime_manifest_errors()`, reachable from
  `validate_capabilities()`/`mrag validate` where nothing is constructed. It can only take a
  declared role at face value, so it is advisory: **necessary, not sufficient**.
- `_wired_capability_evidence()` runs at the end of `ComponentRegistry.wire()`, against the
  components actually built, with the Protocol validation above. This is the authoritative gate:
  a manifest that passes the dry-run can still be rejected here.

Neither is ever used to build a `ConformanceReport` — a capability is not evidence, and
conflating the two is exactly what an earlier version of this lot got wrong. `orchestration/` may
import only `core/`+`contracts/`+`orchestration/` (ADR-0007 §6), so it cannot construct
`LangGraphEngineAdapter` (in `adapters/`) in any case. Absent `assurance.min_level`, no check
runs — the same optionality every other governance/observability section already has.

### What the gate promises, precisely

`assurance.min_level` answers **"are the controls this level requires declared, wired, and
structurally conformant?"** — nothing more. Protocol membership validates method *presence*, not
signatures and not behaviour, so a control that implements the right names and enforces nothing
(an `enforce_query()` that returns `None` for a missing tenant) passes the gate. That limit is
inherent to startup-time validation, which must not execute governance decisions during `wire()`,
and is an [ADR-0017 §9](../adr/0017-engine-independent-assurance-contract.md) accepted risk
recorded on 2026-09-11 — not a defect to route around.

Proving a control *enforces* is the conformance harness's job, not the gate's:
`tests/contract/test_engine_conformance.py` certifies a claim at `ENFORCED` only when a denied or
failing control demonstrably fails the request, and at `VERIFIED` only when the framework itself
rejects fabricated evidence. **An operator wiring a third-party control at L2 must run that
harness against it**; a green startup gate is evidence of wiring, not of enforcement.

Full evidence: `docs/refactoring/lot-21-engine-independent-assurance-contract.md`.

## Cancellation, concretely

`CancellationToken` is a plain mutable object, not a dataclass — cancellation is inherently
cross-task shared state, which frozen/dataclass semantics don't fit. An adapter that declares
`EngineCapability.CANCELLATION` must check `context.cancellation_token.is_cancelled` at every
reasonable step boundary and raise `EngineCancelledError` promptly; the Lot 6 spike evidence
(`docs/refactoring/lot-6-spike/README.md`) already flagged that for a sync-blocking underlying
call, "promptly" may only mean the *caller* stops waiting, not that the underlying work is
actually killed — that distinction is an adapter-level resource-cleanup concern, not something
this contract can guarantee on the engine's behalf.
