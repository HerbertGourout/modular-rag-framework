# Lot 8 — Native V1 Adapter and Compatibility Facade

**Status:** COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 7 (`DocumentEngine` port)

## What was done

- **`orchestration/native_engine.py`**: `NativeEngineAdapter`, wrapping `RAGEngine` behind the
  `DocumentEngine` port. Declares an **empty capability set** deliberately — `RAGEngine.answer()`
  has no native streaming, cancellation, or tool-use, and its own internal `SecurityGuard` check
  (wired via the manifest) is a separate, pre-existing mechanism, not the same thing as the
  port's `GovernanceHook`. Overclaiming a capability this adapter can't honor would be worse than
  declaring none.
- **`app/bootstrap.py`**: `load_native_engine(path)` added alongside the existing
  `load_pipeline(path)`. `load_pipeline()` is untouched — the compatibility route. "Rollback"
  from the adapter is simply calling `load_pipeline()` instead; both start from the identical
  `ComponentRegistry.wire()` output, so switching between them changes nothing about which
  components actually run.
- **Removed private-container access from every interface that had it** (the gap Lot 4 found and
  this lot's own explicit job):
  - `RAGEngine` gained three public, read-only properties: `manifest_id`, `chunker`, `retriever`.
  - `api/__init__.py`: `pipeline._c.manifest.id` → `pipeline.manifest_id`.
  - `cli/__init__.py`: `pipeline._c.chunker` → `pipeline.chunker`.
  - `examples/hybrid_search/main.py`: `pipeline._c.retriever` → `pipeline.retriever` (found
    during this lot's own private-access sweep, not previously in the gap matrix — the
    `HybridRetriever._vector`/`._bm25` introspection one line below it was deliberately left
    alone: it's already commented as an intentional demo exception, and fixing it would mean
    redesigning `HybridRetriever`'s own public API, which is out of this lot's scope).
- **Fixed the `POST /answer` routing bug** (found in Lot 4, assigned to this lot in the gap
  matrix): moved `QuestionRequest`/`AnswerResponse` from locally-scoped classes inside
  `create_app()` to module level. Confirmed by direct reproduction before and after — 422 before,
  200 after, identical `_FakePipeline` fixture.
- **Updated the Lot 4 tests that characterized both bugs** to be regression tests instead:
  `tests/unit/api/test_api.py`, `tests/unit/cli/test_cli.py`, `tests/unit/app/test_bootstrap.py`
  — fakes changed from mimicking `_c` to mimicking the new public properties; docstrings/test
  names updated from "characterizes the bug" to "regression test for the fix."
- **`tests/unit/orchestration/test_native_engine.py`** (new, 8 tests): Protocol conformance,
  capabilities correctly empty, a governance hook and a pre-cancelled token both correctly
  *ignored* (not mishandled) since neither capability is declared, `arun`/`astream` behavior, and
  — the actual point of this lot — a **parity test** proving `NativeEngineAdapter.run()` produces
  the same answer text as calling `RAGEngine.answer()` directly with identical fakes.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 270 tests total (211 unit + 59 contract, up from 261) — the +9 are the new adapter tests plus
  updated fixtures in existing files; no test was deleted, several were renamed/updated in place.
- mypy baseline unchanged at 35.
- Manually reproduced the `/answer` 422→200 fix with a standalone repro script before touching
  the test suite, to confirm the fix works independent of the test fixtures themselves.
- `grep` swept the whole repo for `pipeline._c`/`engine._c` after the fix — zero remaining
  matches outside `orchestration/engine.py` itself (where `RAGEngine` legitimately uses its own
  private attribute) and historical docstring references in the updated test files.

## Lot 8 acceptance (per `docs/refactoring-plan.md` §6)

"V1 parity; no interface private-state access; compatibility route and rollback flag" — all
three satisfied: parity proven by test, private-container access eliminated repo-wide (not just
in the two files Lot 4 flagged), `load_pipeline()` is the compatibility route and reverting to
it *is* the rollback mechanism (documented in `load_native_engine()`'s own docstring rather than
built as a separate unused feature flag, since nothing is switched over to the adapter in
production yet — api/cli still call `load_pipeline()`/`RAGEngine` directly, unchanged).

## Next

Lot 9 (versioned solution configuration) and Lot 10 (trace/audit foundation, PostgreSQL-backed)
both depend on Lot 7, not Lot 8, and can proceed independently of whether/when api or cli
actually switch to `load_native_engine()` — that migration isn't required by this lot and wasn't
done here, to keep the change proportionate to what was asked.
