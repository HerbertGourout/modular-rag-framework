# Lot 4 (Part 1 of 2) — Public Surface Characterization: API, CLI, Manifest Loading, Registry

**Status:** IN PROGRESS (this slice complete; metrics/deletion-update/hybrid-fallback slice remains)
**Date:** 2026-08-04
**Depends on:** Lot 3
**Scope decision:** the user chose to split Lot 4 — public surface proper (API, CLI, manifest
loading, registry wiring) first, since it's where concrete problems were already visible;
metrics/deletion-update/hybrid-fallback characterization is a separate follow-up session.

## What was done

Added 28 characterization tests across 5 new files (none of these surfaces had any test
coverage before this lot — `orchestration/`, `api/`, `cli/`, and `app/` were all at 0%):

- `tests/unit/orchestration/test_registry.py` (6 tests) — `ComponentRegistry.wire()`: required
  vs. optional component roles, `RegistryError` on an unknown type (message format), silent
  overwrite on duplicate registration, the post-wiring private-attribute injection
  (`retriever._embedder`, `retriever._store`), and the documented built-in type names in
  `ComponentRegistry.default()`.
- `tests/unit/orchestration/test_engine.py` (8 tests) — `RAGEngine.answer()`/`retrieve()`/
  `ingest_chunks()`: trace steps emitted (`retrieve`, `generate`, `guard_query`/`guard_answer`
  when a guard is configured), `SecurityError` raised when a guard blocks query or answer,
  embedding-on-ingest behavior (only chunks without an existing embedding get one), and how
  ingestion feeds the retriever's lexical (`.index()`) side.
- `tests/unit/app/test_bootstrap.py` (4 tests) — `load_manifest()`: `ManifestError` on a missing
  file and on invalid YAML, schema validation against `PipelineManifest` defaults;
  `load_pipeline()` end-to-end via `ComponentRegistry.default()` with real built-in adapter type
  names (confirmed safe for unit scope — every adapter here lazy-loads its heavy dependency on
  first *use*, not at construction, so no network/model I/O happens).
- `tests/unit/api/test_api.py` (5 tests) — see "New finding" below; also covers `/health`'s
  private-container read, `/retrieve`'s 300-char content truncation, the exception-leak gap, and
  the absence of any authentication on any route.
- `tests/unit/cli/test_cli.py` (5 tests) — `mrag version`/`ask`/`ingest`: happy paths, the
  required `--manifest` option's usage-error behavior, and the same private-container access
  pattern (`pipeline._c.chunker`) as the API.

## New finding: `POST /answer` does not accept its own documented request body

Not previously in `docs/refactoring-plan.md` §2 ("API security" only listed exception leakage
and missing auth/rate limits) — this is more severe than either of those, found while writing
`test_answer_route_does_not_accept_the_documented_json_body`.

**Root cause:** `src/modular_rag/api/__init__.py` has `from __future__ import annotations` at
module level *and* defines `QuestionRequest`/`AnswerResponse` as classes local to
`create_app()`. Under postponed evaluation, the route signature `def answer(req:
QuestionRequest)` is stored as the bare string `'QuestionRequest'`. FastAPI resolves that
forward reference against the function's module globals, where a locally-scoped class does not
exist, fails silently, and falls back to treating `req` as a required, unresolvable **query**
parameter instead of a request body.

**Effect:** `POST /answer` with the documented `{"question": "..."}` JSON body returns
`422 Unprocessable Entity` (`detail: [{"loc": ["query", "req"], "msg": "Field required"}]`) — not
the 200 the API's own code and any caller following its shape would expect. Forcing `req` as a
query parameter instead doesn't help either: it then raises an *unhandled*
`pydantic.errors.PydanticUserError: ...ForwardRef('QuestionRequest')... is not fully defined`,
an uncaught 500 with no `try/except` around it. **The endpoint has likely never worked
end-to-end via HTTP.** Confirmed via `route.endpoint.__annotations__` (shows the raw string, not
the class) and by calling the handler function directly — bypassing FastAPI's parameter
resolution entirely — which proves the handler's own logic (including the already-known
exception-leak behavior) is otherwise correct.

**Not fixed here** — Lot 4 characterizes current behavior; this is now recorded as a concrete
regression test (`test_answer_route_does_not_accept_the_documented_json_body`) so whichever lot
fixes it (Lot 8, when private-container/interface access is cleaned up, is the natural place)
has a red-to-green test ready. **Action taken in this lot:** added a new row to
`docs/refactoring-plan.md` §2 gap matrix for this finding — see tracker diff.

## Verification

- `./scripts/check.sh full` — all 6 steps pass.
- 227 total tests now pass (179 unit + 48 contract), up from 199 before this lot (151 unit + 48
  contract) — 28 new, 0 broken.
- mypy baseline unchanged at 35 (no new type errors introduced by the new test files).

## Remaining for Lot 4 (Part 2, not started)

Per `docs/refactoring-plan.md` §5, Lot 4 still needs characterization for: metrics behavior
(`eval/`), document deletion/update semantics, and hybrid-retrieval fallback — none of which
this slice touched. Lot 4's status stays `IN PROGRESS`, not `COMPLETE`, until that's done.
