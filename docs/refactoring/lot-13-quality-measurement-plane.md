# Lot 13 — Quality/Measurement Plane

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** none directly; closes two gaps both originally found in Lot 4.

## What was done

Per `docs/refactoring-plan.md`: "Correct metric vocabulary and formulas with reference fixtures;
version quality and golden-dataset schemas; distinguish infrastructure failure from zero quality;
measure retrieval, answer, evidence, policy, latency, and cost; begin gates in report-only mode
and promote agreed thresholds to blocking with recorded baselines."

### Metric vocabulary correctness

- **`core/models/metrics.py`**: `Metrics` fields are now grouped and documented by what they
  measure — retrieval (`recall_at_k`/`precision_at_k`/`ndcg`/`mrr`, over retrieved chunks vs. a
  relevant-id set), answer (new: `exact_match`, `answer_precision`, `answer_recall`, plus the
  existing `answer_relevance`/`groundedness`/`faithfulness`/`context_precision`, all over
  generated-answer-vs-gold), policy (new: `policy_violations`), and cost/latency (unchanged).
  `METRICS_SCHEMA_VERSION = "1.0"` + a `schema_version` field, matching the `Trace`/`AuditEvent`
  versioning pattern from Lot 10.
- **`eval/scorers/exact_match.py`**: fixed the exact bug named in
  `docs/refactoring-plan.md` §2 ("`ExactMatchEvaluator` behaves like token-set F1, not exact
  match; answer precision/recall written into retrieval-named fields"). Two real problems, two
  fixes:
  1. The class computed only token-set precision/recall/F1 and wrote them into
     `Metrics.precision_at_k`/`recall_at_k` — fields `eval/scorers/retrieval_metrics.py` defines
     as retrieval-scoped. Now writes into `answer_precision`/`answer_recall`/`answer_relevance`
     instead; `precision_at_k`/`recall_at_k` are never touched by this evaluator (regression
     test: `test_retrieval_scoped_fields_are_never_touched`).
  2. A class named "exact match" never actually checked for exact equality anywhere. It now also
     computes a genuine `exact_match` field (normalized string equality — lowercased,
     whitespace-collapsed, 1.0/0.0 only), kept separate from the softer token-F1 signal.
     Reference-fixture test: a reordered-and-repeated-token prediction scores perfect
     `answer_precision`/`answer_recall` (the pre-existing, still-legitimate F1 behavior) but
     `exact_match == 0.0` (correctly rejected) —
     `test_reordered_and_repeated_tokens_score_high_f1_but_not_exact_match`.

### Distinguishing infrastructure failure from zero quality

- **`Metrics.failed: bool = False` / `failure_reason: str | None = None`** (new fields) +
  **`Metrics.for_failure(reason)`** classmethod — a case whose engine call raised is now
  recorded distinctly from a case that ran and genuinely scored nothing.
- **`eval/runners/benchmark.py`**: `BenchmarkRunner.run()`'s `except Exception` branch now builds
  `Metrics.for_failure(str(exc))` instead of a bare `Metrics()`. `BenchmarkReport` gained
  `failed_count`/`failure_rate` properties, and `avg_answer_relevance`/`avg_recall` now filter on
  `not m.failed` explicitly (previously this exclusion was only incidental — a failed case's
  bare `Metrics()` happened to have `None` quality fields too, which is no longer assumed, it's
  asserted).

### Versioned golden-dataset schema

- **`eval/runners/benchmark.py`**: `GOLDEN_SET_SCHEMA_VERSION = "1.0"` + `GoldenSet` dataclass
  (`name`, `cases: list[BenchmarkCase]`, `schema_version`, `domain`) — a versioned, named,
  comparable artifact wrapping the pre-existing `BenchmarkCase` list, rather than an anonymous
  `list[BenchmarkCase]` a caller has to track separately. Deliberately does not invent a new,
  disconnected golden-case format — `BenchmarkCase` was already the framework's real golden-case
  shape, just unversioned; this lot versions it in place rather than duplicating it.

### Report-only / blocking quality gates

- **`eval/quality_gate.py`** (new): `QualityGate(baseline, mode=REPORT_ONLY|BLOCKING, tolerance=0.0)`.
  `check(actual: dict[str, float])` compares against the recorded baseline; `REPORT_ONLY` never
  raises (the caller inspects the returned `GateResult`), `BLOCKING` raises `QualityGateError`
  (carrying the full `GateResult`, not just the first violation) on any regression past
  `tolerance`. A metric present in the baseline but missing from `actual` is treated as `0.0` —
  fail-closed, matching this whole programme's established convention (an unexpectedly-absent
  metric looks like a regression, not a silent pass).
  - Deliberately generic over `dict[str, float]` rather than hardcoded to `BenchmarkReport`:
    `BenchmarkReport.quality_summary()` is the intended source, and deliberately excludes
    `failure_rate` (lower-is-better — the opposite comparison direction from every other metric
    this gate supports; gating on it needs different logic, not shoehorned into this one).

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 471 tests total (389 unit + 82 contract, up from 457 at Lot 12c).
- mypy baseline unchanged at 34.
- Reference-fixture tests for both metric families (exact-match vs. token-F1 divergence;
  quality-gate pass/fail/tolerance/missing-metric cases) prove the *formulas*, not just that the
  code runs.

## What "measure retrieval, answer, evidence, policy, latency, and cost" covers today

| Dimension | Field(s) | Status |
|---|---|---|
| Retrieval | `recall_at_k`, `precision_at_k`, `ndcg`, `mrr` | Implemented (`eval/scorers/retrieval_metrics.py`, pre-existing) |
| Answer | `exact_match`, `answer_precision`, `answer_recall`, `answer_relevance` | Implemented this lot |
| Evidence | `groundedness`, `faithfulness`, `context_precision` | Fields exist; `groundedness`/`faithfulness` are not wired into any evaluator yet (`GroundednessValidator` is a separate, RAGEngine-unconnected lexical-support gate — see Lot 11c's own honesty note about the same disconnect) |
| Policy | `policy_violations` | Field added this lot; nothing populates it yet — no evaluator or engine path counts policy violations into a `Metrics` object today |
| Latency/cost | `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd` | Fields exist; populated by generators' own `Trace` instrumentation (Lot 10), not yet copied into `Metrics` by any evaluator |

Recorded honestly, not silently overclaimed: this lot corrects the *vocabulary and failure
semantics* of the measurement plane and adds the gate mechanism the plan asks for. It does not
retroactively wire every dimension's field into a populating code path — `policy_violations` and
the evidence/cost fields exist as measurement *capacity*, consistent with several other lots this
session (e.g. Lot 11c's `HumanReviewGate`) that build real, tested infrastructure ahead of a
producer that populates it.

## Lot 13 acceptance (per its own description in `docs/refactoring-plan.md`)

"Correct metric vocabulary and formulas with reference fixtures; version quality and
golden-dataset schemas; distinguish infrastructure failure from zero quality... begin gates in
report-only mode and promote agreed thresholds to blocking with recorded baselines" — all
delivered. "Measure retrieval, answer, evidence, policy, latency, and cost" — retrieval and answer
are fully wired end-to-end; evidence/policy/cost have schema capacity without a populating
producer yet, honestly recorded above rather than claimed complete.

## Next

Lot 14 (reliability/concurrency/resource lifecycle): sync/async execution semantics, timeouts,
retry eligibility, cancellation, circuit breaking, backpressure, graceful shutdown, and
concurrency-safety for the mutable in-memory state this whole session has been building on top of
(`BM25Retriever._chunks`, `InMemoryLifecycleLedger._records`, `InMemoryAuditSink._events`, etc.).
