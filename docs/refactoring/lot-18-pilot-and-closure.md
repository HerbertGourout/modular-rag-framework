# Lot 18 — Pilot Comparison, CI Hardening, and Programme Closure

**Date:** 2026-08-05
**Status:** Engineering scope COMPLETE. Sign-off is explicitly **not** self-granted — see
"What this lot cannot do" below.

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Run a sanitized representative scenario with native and external engines under the same
> governance and quality profiles. Compare delivery effort, quality, latency, cost, audit
> evidence, concurrency, deployment, data migration, and rollback. Harden all approved CI
> gates, remove expired shims, publish release evidence, and obtain architecture, security,
> operations, legal, and business-quality sign-off.

Acceptance bar (§6): "Pilot and rollback exercise pass; mandatory gates green; named owners
sign final evidence."

## The pilot scenario — and a real bug it found

New `scripts/pilot_engine_comparison.py`: runs identical synthetic (non-sensitive) queries
through both `DocumentEngine` adapters (`NativeEngineAdapter`, `LangGraphEngineAdapter`)
against the *same* wired `Container` — same guard, same tenant policy, same fake retriever/
generator. No live LLM or Qdrant call: this environment has no API keys or reachable Qdrant, and
"sanitized" already excludes real customer data, so a genuinely live-infra pilot isn't possible
here (same category of constraint as Lot 16c). What real in-process fakes over both real adapter
implementations *can* still prove — and did:

**Running it surfaced a genuine governance-parity bug that had shipped in Lot 15 and survived
through Lots 16-17 undetected.** `LangGraphEngineAdapter._node_retrieve()` only *filtered*
retrieved chunks when `query.tenant_id` happened to be set — it never called
`tenant_policy.enforce_query()` to fail closed when a query had **no** tenant_id at all, unlike
`RAGEngine`/`NativeEngineAdapter`, which deny that case before retrieval ever runs (Lot 11b). A
tenant_policy-enabled deployment would have silently *answered* an untenanted request through
the LangGraph adapter while correctly denying the identical request through native — the exact
class of parity bug Lot 15's own acceptance bar ("must pass the same governance... tests as
native V1") existed to prevent, and the exact class of bug Lot 15 *did* catch and fix for
`Container.guard` denial, but this second, separate enforcement point was missed. Root cause:
Lot 15's own test suite covered tenant *filtering* (chunks present, tenant_id set — filters
correctly) and *propagation* (`ExecutionContext.tenant_id` fills in a missing `Query.tenant_id`)
but never the fail-closed "no tenant_id anywhere" case specifically.

Fixed: `_node_retrieve()` now calls `tenant_policy.enforce_query(query)` before retrieval,
identical to `RAGEngine._run_steps()`'s step 0. Two new regression tests in
`tests/unit/adapters/llms/test_langgraph_engine.py`:
`test_tenant_policy_denies_when_no_tenant_id_is_set_anywhere` and
`test_parity_with_native_adapter_on_a_missing_tenant_id` (a same-container parity test, mirroring
Lot 15's own `test_parity_with_native_adapter_on_a_guard_denial` pattern exactly). All 20 tests
in that file pass after the fix.

This is the clearest demonstration in the whole programme of why Lot 18's "run a scenario"
requirement is not redundant with the per-lot unit tests that came before it: the bug lived
exactly in the gap between two adapters' test suites, invisible to either one in isolation, and
only surfaced by actually exercising both engines side by side.

## Comparison across the nine dimensions

Built from real evidence already produced across Lots 6-17, not invented for this lot — cited
per dimension:

| Dimension | Native (`NativeEngineAdapter`) | LangGraph (`LangGraphEngineAdapter`) |
|---|---|---|
| **Delivery effort** | Lower — wraps the existing `RAGEngine` wholesale (Lot 8, ~1 week per the sizing table). | Higher — required understanding LangGraph's `StateGraph` API, building 5 nodes, and two rounds of governance-parity debugging (Lot 15's guard-denial bug, this lot's tenant-denial bug). Second adapters cost more per unit of new capability than the first, as expected. |
| **Quality** | Identical output for identical inputs — `test_parity_with_native_adapter_on_the_happy_path` (Lot 15) proves byte-identical `Answer.text` against the same fake generator. No live-LLM quality comparison was possible in this environment (no API keys) for either adapter. |
| **Latency** | ~9ms mechanism overhead in the pilot run (fake components, no network). | ~640ms on the *first* call (one-time `StateGraph.compile()`, cached in `self._graph` thereafter — see `_get_graph()`), then comparable per-call overhead. Real per-request latency under a live LLM is dominated by the LLM call itself for both adapters; this pilot cannot measure that without live API access. |
| **Cost** | No direct engine-level cost difference — both call the same configured `Generator`. | Same. LangGraph adds a build-time dependency footprint (`langgraph`, transitively `langchain-core` per ADR-0006's own risk note) but no per-request cost delta. |
| **Audit evidence** | `RAGEngine` emits `AuditEvent`s (`RUN_SUCCEEDED`/`RUN_FAILED`/`GUARD_DECISION`, Lots 10/11c) when `Container.audit_sink` is configured. | **Still does not**, by Lot 15's own explicit, documented design decision: audit emission belongs above the `DocumentEngine` port, at whatever calls `load_engine()`, which doesn't exist yet. Recorded as open in Lot 15's own decision record and never picked up since — genuinely still open at programme closure, not silently resolved. |
| **Concurrency** | Both share Lot 14's component-level thread-safety (locks on the four in-memory reference stores) — this is `Container`-level, not adapter-level, so it applies identically regardless of which adapter is selected. Neither adapter adds its own concurrency handling beyond what its underlying engine (a Python call stack vs. LangGraph's own runtime) provides natively. |
| **Deployment** | Same container image, same manifest-driven selection (`engine.adapter` field, Lot 15) — no separate build or deployment artifact needed for either engine (Lot 16b/16c). |
| **Data migration** | N/A to engine choice directly — index/ledger schema versioning (Lot 12b/12c) is engine-agnostic; both adapters read the same wired components. |
| **Rollback** | Proven trivial in both directions — a single manifest field (`engine.adapter: "native"` vs. `"langgraph"`), covered by `test_a_v1_manifest_migrated_to_v2_and_switched_to_langgraph_loads_correctly` (Lot 15) and documented in `docs/guides/backup-restore.md` (Lot 16c). |

## CI hardening — a real gap found and fixed

Auditing the CI workflow for this lot's "harden all approved CI gates" found a genuine,
previously-undetected defect: **`langgraph` was never installed in the `test-unit` or
`coverage` jobs** (`.github/workflows/ci.yml`, both installed `.[v1,dev]` only). Since
`tests/unit/adapters/llms/test_langgraph_engine.py` (Lot 15, 20 tests, now 22 after this lot's
fix) calls `LangGraphEngineAdapter.run()`/`.astream()` for real, which lazy-imports the actual
`langgraph` package on first call, every one of those tests would fail with
`ModuleNotFoundError` on an actual CI run — undetected until now because this workflow's
`test-unit`/`coverage` jobs, specifically, had never actually been exercised against this test
file in a real CI environment (only this session's local `check.sh full`, which uses a
`[all,supply-chain]`-installed venv, ran them). Fixed: both jobs now install
`.[v1,langgraph,dev]`. **Not independently re-verified against a truly isolated fresh venv** —
attempting one hit an unrelated pip-resolver error in this sandboxed environment
(`InvalidVersion: 'all'`, traced to editable-install metadata resolution, not to this change);
confidence in the fix instead rests on (a) Lot 17's own dependency audit already confirming zero
`v3`/`v4`/`v5`-only imports exist anywhere `tests/unit/` would exercise, and (b) this session's
own venv (which does have `langgraph` installed) passing all 22 tests. The next real CI run on
GitHub Actions is the actual verification this fix has been waiting for, same as Lot 16b's
`container-build` job.

## Expired shims: none found

Checked every reference to "compatibility facade"/"deprecat"/"shim"/"support window" across
`src/modular_rag/` and `docs/refactoring-plan.md`. The one real compatibility facade in this
codebase — `app/bootstrap.py`'s `load_pipeline()` (Lot 8, "the stable compatibility facade") —
was never given a deprecation date or support window; its own docstring calls it "stable," not
"deprecated." §8.8's migration principle requires "non-use evidence... and a tested restoration
commit" before removal, and §8.2 requires introducing a facade *before* migrating callers away
from what it replaces — neither step has happened for `load_pipeline()` (it is still the
primary entry point `api/__init__.py` and `cli/__init__.py` both use). There is nothing to
remove here: an item can only be an "expired shim" if a deprecation window was actually started
and has since lapsed, and none has been, for anything in this codebase. Recorded as a genuine
"none found" rather than skipped silently.

## Release evidence

Compiled in `CHANGELOG.md`'s `[Unreleased]` section (new entry summarizing Phase A-D of the
refactoring programme, linking to all 18 lots' individual decision records under
`docs/refactoring/`) rather than duplicated here. `docs/refactoring-plan.md` itself is the
full evidence trail — every lot's row in its decision log and change history cites the exact
file where that lot's proof lives.

## What this lot cannot do

**Sign-off is not self-granted.** §6's acceptance bar for Lot 18 requires "named owners sign
final evidence" across architecture, security, operations, legal, and business-quality — and
`docs/refactoring/lot-0-baseline.md` §2 already establishes that decision authority in this
programme is sole (Herbert Gourout), not distributed across role-labeled reviewers an agent
could impersonate. An agent producing a self-signed "architecture: ✅ approved, security: ✅
approved..." block would not be evidence of review — it would be a fabricated approval with no
one behind it, exactly the kind of unsupported claim `docs/refactoring-plan.md` §1.4's own
programme invariant ("No planned capability is described as delivered") exists to prevent. What
this lot *does* provide, honestly, is the compiled evidence a real reviewer needs: this
document, the nine-dimension comparison above, the pilot script and its output, and the full
`docs/refactoring/lot-{0..18}-*.md` trail. The actual sign-off — architecture, security,
operations, legal, business-quality — is Herbert Gourout's to give, not this lot's to claim.

Two items also remain genuinely open, not resolved by claiming otherwise:
- LangGraph adapter audit-evidence parity (recorded above under "Audit evidence").
- The two Lot 16b escalations (`pymupdf` AGPL licence, 56 research PDFs' redistribution
  rights) — both explicitly confirmed "leave as-is for now," not resolved, not this lot's to
  reopen.

## Verification

`./scripts/check.sh full` — all 7 steps pass (mypy baseline unaffected, 31/31). Unit test count
464 → 466 (two new regression tests added to `test_langgraph_engine.py`, whose own total goes
20 → 22). `python scripts/pilot_engine_comparison.py` executed for real in this environment
(output captured above and in this lot's evidence) — the one genuinely "run a scenario"
deliverable in this lot that needed no live infra to produce real findings.

## Tracker updates

- Header status block: Lot 18 → engineering scope COMPLETE, sign-off pending.
- Acceptance-criteria row for Lot 18 annotated with what's actually been demonstrated vs. what
  requires a human.
- Decision log + change history: new Lot 18 entry.
- `CHANGELOG.md`: new `[Unreleased]` entry for the full refactoring programme.
