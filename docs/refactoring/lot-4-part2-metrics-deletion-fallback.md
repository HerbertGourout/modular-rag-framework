# Lot 4 (Part 2 of 2) — Metrics, Deletion/Update, Hybrid Fallback Characterization

**Status:** COMPLETE — Lot 4 as a whole is now COMPLETE (Part 1 + Part 2)
**Date:** 2026-08-04
**Depends on:** Lot 4 Part 1 (`docs/refactoring/lot-4-public-surface-part1.md`)

## What was done

23 new characterization tests across 6 files (2 new, 4 extended):

- `tests/unit/retrieval/test_bm25.py` (new, 7 tests) — `BM25Retriever` had zero direct tests
  before. Covers empty-before-index, ranking by term overlap, zero-score exclusion, full-replace
  (not incremental) semantics on re-`index()`, the missing `delete()`/`clear()` methods, and
  `aretrieve()` delegation. **Includes the small-corpus finding below.**
- `tests/unit/retrieval/test_hybrid.py` (extended, +2 tests) — both-sources-fail returns `[]`
  without raising (silent double-failure); `HybridRetriever` mutates a nominally `frozen=True`
  `RetrievedChunk`'s `rank`/`retrieval_method` via `object.__setattr__` after fusion.
- `tests/unit/eval/test_retrieval_metrics.py` (new, 7 tests) — `recall_at_k`, `precision_at_k`,
  `mrr`, `compute_retrieval_metrics`; this module had 0 direct tests despite existing (35% line
  coverage, all from incidental import-time execution).
- `tests/unit/eval/test_benchmark.py` (new, 4 tests) — `BenchmarkReport` aggregation (None-value
  handling) and `BenchmarkRunner.run()`, including the silent-failure gap below.
- `tests/unit/eval/test_exact_match.py` (extended, +1 test) — names the existing
  naming/behavior mismatch explicitly (reordered + repeated tokens score a "perfect" 1.0/1.0,
  which true exact-match never would).
- `tests/unit/orchestration/test_engine.py` (extended, +2 tests) — `RAGEngine` has no `delete()`
  method at all; deleting via `container.indexer.delete(ids)` directly (the only path that
  exists) never touches the retriever's own lexical state.

## New finding: BM25 silently returns zero hits for a relevant document in a small corpus

**Not previously documented.** `rank_bm25`'s IDF term can be zero or negative when a query term
appears in most/all documents of a small corpus — trivially likely with only 1-2 chunks indexed
(a small `examples/simple_qa/`-scale demo, or any small real deployment). Confirmed directly
against `rank_bm25.BM25Okapi`:

- 1-document corpus, query matching that document's own content → score **-0.824** (negative).
- 2-document corpus, query matching one of the two → score **0.0** for both.
- 5-document corpus (varied content) → the correctly-matching document scores **3.33**, others
  **0.0** — ranking works fine once the corpus is large/diverse enough.

`BM25Retriever.retrieve()` filters on `if score > 0`, so a document that is the best (or only)
match for a query is silently dropped in exactly the small-corpus case most likely to appear in
a demo, a test fixture, or an early-stage real deployment. Characterized in
`test_retrieve_returns_no_hits_for_a_relevant_document_in_a_too_small_corpus`; **added as a new
row in `docs/refactoring-plan.md` §2** (see tracker diff). Not fixed here — a candidate for
Lot 12b or an upstream IDF-floor workaround.

## New finding: benchmark failures are indistinguishable from genuine null scores

`BenchmarkRunner.run()` catches *any* exception from `engine.answer()`, logs a warning, and
appends a bare `Metrics()` (all fields `None`) for that case — the same shape a
legitimately-scored-but-null case would have. `report.avg_answer_relevance` silently averages
only over the surviving cases, so a 50%-failure-rate benchmark run reports the same average as a
50%-genuinely-poor-scoring run. This directly matches the existing
`docs/refactoring-plan.md` §10.4 invariant ("Benchmark infrastructure failures fail the run;
they do not produce empty metrics") — confirming that invariant is not yet upheld by the code.
Not fixed here (Lot 13 owns metric/benchmark correctness); characterized in
`test_runner_swallows_engine_failures_into_indistinguishable_empty_metrics`.

## Verification

- `./scripts/check.sh full` — all 6 steps pass.
- 250 total tests now pass (202 unit + 48 contract), up from 227 (179 + 48) before this slice —
  23 new, 0 broken.
- mypy baseline unchanged at 35 (no new type errors).

## Lot 4 acceptance (per `docs/refactoring-plan.md` §6)

"Every identified public surface and critical failure path has characterization evidence" —
across both parts: API, CLI, manifest loading, registry wiring, RAGEngine's core flow, metrics
(exact-match + retrieval metrics + benchmark runner), document deletion/update, and hybrid
retrieval fallback all now have direct characterization tests. Three real, previously
undocumented bugs were found and recorded rather than silently fixed: the `/answer` routing bug
(Part 1), the BM25 small-corpus scoring gap, and the confirmation that benchmark failure-masking
is real (not just a theoretical risk already named in §10.4). Lot 4 status → `COMPLETE`.
