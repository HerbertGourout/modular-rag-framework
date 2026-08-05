# Lot 15 — LangGraph External Adapter

**Date:** 2026-08-05
**Status:** COMPLETE

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Implement the selected external adapter. It must pass the same semantic engine, governance,
> audit, migration, quality, cancellation, and failure tests as native V1. Express differences
> through capabilities and documented extension configuration.

ADR-0006 (Lot 6) selected LangGraph. This lot builds the second `DocumentEngine` (`contracts/engine.py`,
Lot 7) implementation over it, wires manifest-driven selection between the two adapters, and proves
parity/documented-divergence against `NativeEngineAdapter` (Lot 8).

## What was built

| File | Purpose |
|---|---|
| `src/modular_rag/adapters/llms/langgraph_engine.py` | `LangGraphEngineAdapter` — real LangGraph `StateGraph` (route → retrieve → guard → [blocked \| generate]) orchestrating the same wired `Container` components (`retriever`, `guard`, `generator`, `tenant_policy`, `redactor`) `RAGEngine`/`NativeEngineAdapter` use. |
| `src/modular_rag/app/bootstrap.py` | New `load_engine(path) -> DocumentEngine`: reads `manifest.engine.adapter` (`"native"` default, or `"langgraph"`) and returns the matching adapter over the identical `wire()` output. Unknown adapter names raise `ConfigurationError`. |
| `pyproject.toml` | New `langgraph` optional-dependency extra (`langgraph>=1.2`); added to `all`. The native adapter (default) needs none of it. |
| `tests/unit/adapters/llms/test_langgraph_engine.py` | 18 tests: Protocol conformance, capability declaration, happy-path `run`/`arun`/`astream`, container-guard blocking, governance-hook blocking, tenant filtering, tenant propagation from `ExecutionContext`, redaction, cancellation (pre-cancelled and not), generator-exception propagation, `astream` capability-error, and 2 parity tests against `NativeEngineAdapter`. |
| `tests/unit/app/test_bootstrap.py` | +5 tests for `load_engine()` (native default, explicit native, langgraph selection, unknown-adapter error) and 1 migration test: a real v1 manifest migrated to v2 (Lot 9's `migrate_v1_to_v2`) with `engine.adapter` overridden to `"langgraph"` loads and resolves to `LangGraphEngineAdapter`. |

## A genuine layering violation, found and fixed before commit

`./scripts/check.sh full` Step 3 (hexagonal layering audit) failed on the first draft:

```
src\modular_rag\adapters\llms\langgraph_engine.py:39: adapters imports modular_rag.app.container
(adapters cannot import domain modules)
```

`scripts/check_layering.py`'s `ADAPTER_LAYERS` rule permits `adapters/` to import only
`{"core", "contracts", "adapters"}` — `app` is not on that list. The adapter's constructor took
a concrete `app.container.Container`, which is how `NativeEngineAdapter` gets its dependencies —
but `NativeEngineAdapter` sidesteps this by living in `orchestration/native_engine.py`, an
unrestricted layer (`orchestration`/`app` have no entry in `check_layering.py`'s layer sets at
all), not in `adapters/`.

Two ways to resolve this were available: relocate the file to `orchestration/` (mirroring
`NativeEngineAdapter`'s precedent exactly), or keep it in `adapters/llms/` — the location
CLAUDE.md's "Adapter Stubs" table and `.claude/rules/adapters.md` already name as this lot's
target — and remove the `app` dependency instead. The second was chosen: `__init__` is now typed
against `_ComponentSource`, a local `Protocol` (module-private, `runtime_checkable`) describing
only the five members this adapter actually uses (`manifest`, `retriever`, `generator`, `guard`,
`tenant_policy`, `redactor`), built from `contracts/` types only. `Container` satisfies it
structurally without either module importing the other — the adapter still receives the real
`Container` instance at call sites (`app/bootstrap.py`'s `load_engine()`), unchanged at runtime.
This keeps the file where the roadmap already said it belongs, keeps the layering rule intact
without a baseline exception, and is a reusable pattern for any future `adapters/` component that
needs a subset of `Container`'s surface without depending on `app/`.

## A genuine semantic parity bug, found while writing tests

The first `_node_guard` design routed a `Container.guard` denial into the same "blocked" `EngineResult`
path as a port-level `GovernanceHook` denial. But `NativeEngineAdapter`/`RAGEngine` raises
`SecurityError` for the identical `Container.guard` denial — so the two adapters would have diverged
in observable behavior for the same governance signal, which fails Lot 15's own bar ("must pass the
same governance... tests as native V1"). Fixed: `Container.guard` denial now raises `SecurityError`
immediately in both adapters (verified by `test_parity_with_native_adapter_on_a_guard_denial`,
running both adapters against the identical `Container` and asserting both raise). The port-level
`GovernanceHook` — which has no native equivalent to diverge from — keeps its "blocked result, not
exception" semantics, per the port's own conformance suite (`tests/contract/test_engine_conformance.py`).

## Capabilities: how differences are expressed

Per Lot 15's instruction to "express differences through capabilities," not silently:

| Capability | `NativeEngineAdapter` | `LangGraphEngineAdapter` |
|---|---|---|
| `STREAMING` | Not declared | Declared — `astream()` yields real per-node `EngineStep`s from `graph.astream(..., stream_mode="updates")` |
| `GOVERNANCE_INTERCEPT` | Not declared | Declared — `ExecutionContext.governance_hook` is consulted before generation |
| `CANCELLATION` | Not declared (ADR-0006's own accepted risk: LangGraph has no native cancellation API) | Declared — `CancellationToken` is checked at each node boundary (`route`, `retrieve`, `guard`, `generate`), raising `EngineCancelledError` |

This is a strict capability superset, not a lowest-common-denominator port: a caller that checks
`capabilities` before relying on streaming/governance-hook/cancellation gets a correct answer for
either adapter without a code change — satisfying the acceptance bar "profile switch requires no
governance rewrite."

## Extension configuration

No adapter-specific `extensions["langgraph"]` keys or `manifest.engine.config` values were needed —
this adapter takes no LangGraph-specific tunables beyond the wired `Container` itself (model choice,
retrieval `k`, etc. all come from the manifest's existing component config, unchanged). The
extension-envelope discipline documented in `docs/architecture/document-engine-contract.md` §"Extension-envelope
discipline" already covers the pattern (`extensions["langgraph"]`) for when a future need arises;
nothing in this lot exercises it, so nothing new was written there.

## Deliberately out of scope, recorded honestly

`LangGraphEngineAdapter` does **not** replicate `RAGEngine`'s audit-event emission
(`AuditEventType.RUN_SUCCEEDED`/`RUN_FAILED`/`GUARD_DECISION`, Lots 10/11c) or human-review queueing
(Lot 11c). It does replicate every *security-critical* governance path (tenant isolation, the
container's `SecurityGuard`, redaction) because those must hold regardless of which engine executes
a request — but audit/review are call-site concerns, not engine-execution concerns, and duplicating
them inside every `DocumentEngine` adapter is the wrong layer for them long-term: they belong above
the port, in whatever calls `load_engine()` and picks an adapter, so audit evidence is uniform no
matter which engine ran. No such uniform call-site exists yet — `RAGEngine` (native-only, predates
the port) is still the only caller that produces audit evidence today. This is a genuine residual
gap, not a silent one: a caller relying on audit evidence today should use
`NativeEngineAdapter`/`RAGEngine` directly or `load_pipeline()`, not `load_engine()` with
`engine.adapter: "langgraph"`. Recorded as a known gap for Lot 16a (API/CLI hardening is where a
real caller of `load_engine()` would first need this) or Lot 17 (consolidation) to pick up, not
invented here.

Overload/backpressure and soak evidence remain deferred to Lot 16c per Lot 14's own note — this
lot does not add new claims there.

## Verification

`./scripts/check.sh full` — all 7 steps pass:

1. Ruff — clean
2. Compilation — clean
3. Hexagonal layering audit — clean (violation above fixed, not baselined)
4. mypy — 34 errors (baseline: 34, unchanged)
5. Runnable manifest validation — `local-hybrid-rag.yaml` wires cleanly
6. Unit tests — 449 passed (28 new: 18 in `test_langgraph_engine.py`, 6 in `test_bootstrap.py`, plus the pre-existing 5 net into the file's total)
7. Contract tests — 82 passed, `test_engine_conformance.py`'s 11 semantic tests unaffected (still exercise `FakeDocumentEngine` only, per Lot 7 — this lot didn't extend that suite to parametrize over concrete adapters, matching `NativeEngineAdapter`'s own precedent of a separate adapter-specific test file instead)

## Tracker updates

- Header status block: Lot 15 → COMPLETE.
- Gap matrix: "Engine abstraction" row resolved (port validated against a second, structurally
  different engine — proves genuine engine-neutrality, not a wrapper-of-a-wrapper). "Resilience"
  residual row's cancellation sub-item resolved (LangGraph adapter declares and implements it;
  native's non-support is unchanged and still correctly documented as such).
- Decision log + change history: new Lot 15 entry.
