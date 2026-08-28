# Offline evaluation (golden-set benchmark)

Batch 13 (external plan — "Offline benchmark"). **Numbering collision, noted explicitly per this
project's own convention:** this repo's own [docs/refactoring-plan.md](../refactoring-plan.md)
already has its own, unrelated, already-completed "Lot 13" (a metric-vocabulary fix — corrected
`Metrics`, `ExactMatchEvaluator`, `BenchmarkRunner`'s failure-masking, added `GoldenSet`/
`QualityGate`). The two "Lot/Batch 13"s are different plans with different numbering sequences
that happen to collide on the same number — this document is about the external plan's Batch 13,
which *builds on* the internal Lot 13's foundations rather than duplicating them.

Per [ADR-0008](../adr/0008-offline-evaluation-and-engine-activation.md): everything described
here is a **native, offline, programmatic** evaluation capability, not a runtime pipeline
component. No manifest declares `evaluation:`/`quality.gate:` sections to activate any of this at
answer-time — an expected/gold answer is never a reference the online `RAGEngine.answer()` path
depends on.

This benchmark runs as a separate process (`scripts/run_benchmark.py`), driven from a
`ComponentRegistry`-wired `ApplicationService` exactly like the CLI/API do, but scored entirely
outside the request path.

---

## What it measures

`scripts/run_benchmark.py` loads a small, versioned, synthetic golden set
(`src/modular_rag/eval/datasets/core_v1.yaml`), ingests its corpus, and runs every case through
`ApplicationService.answer()`. Each case is one of two types:

- **`case_type: qa`** — a normal question with an `expected_answer` and (usually)
  `relevant_chunk_ids`. Scored on:
  - **Retrieval**: `recall_at_k`, `precision_at_k`, `mrr`, `ndcg` (binary-relevance NDCG@k,
    exactly per [docs/research/DIGEST-evaluation.md](../research/DIGEST-evaluation.md) #1's
    formula).
    - Computed from `Answer.citations[*].chunk_id` against the case's declared relevant ids —
      **not** from a separate retrieval call. `AnswerEngine` only exposes `answer()`; citations
      are what the generator actually saw, so this needs no `Protocol` change to plumb raw
      retrieved chunks through (see `eval/scorers/retrieval_metrics.py`'s module docstring).
  - **Faithfulness** (`eval/scorers/faithfulness.py`): token-overlap between the answer and the
    cited context passages.
    - **A deterministic lexical proxy, not an LLM-judge score** (RAGAS/ARES/TRACe-style). An LLM
      judge would be non-deterministic and need a paid API call, breaking this benchmark's
      "reproducible, no LLM key" requirement. Documented as a proxy, matching this codebase's
      existing honesty convention for other proxy metrics (e.g. [slo.md](../observability/slo.md)
      §3).
  - **Answer correctness** (`eval/scorers/answer_correctness.py`):
    `difflib.SequenceMatcher.ratio()` against the gold answer.
    - Order/phrasing-sensitive, distinct from `ExactMatchEvaluator`'s bag-of-words
      `answer_relevance` (token-set F1). Also deterministic, no embeddings call.
  - **`exact_match`/`answer_precision`/`answer_recall`/`answer_relevance`** — from the injected
    `ExactMatchEvaluator` (Lot 13, `docs/refactoring-plan.md`), unchanged.
- **`case_type: safety`** — a security probe.
  - `expect_block: true` cases use `BasicSecurityGuard`'s own documented regex families
    (`security/filters/basic_guard.py`), so the expected outcome is deterministic, never an LLM's
    judgment call.
  - One case (`expect_block: false`) is a false-positive probe: wording that superficially
    resembles an attack pattern but must **not** be blocked.
  - Scored as `safety_score` (`1.0`/`0.0` — did the engine behave as expected?), aggregated into
    `safety_pass_rate`.

Every case also records `latency_ms` (wall-clock around the `answer()` call, including a failed
case — Codex review pass 1, HIGH-001 follow-up: `Metrics.for_failure()` previously left this
`None` for every failure branch) and, best-effort, `cost_usd` from
`Answer.metadata.get("cost_usd")`.

**`DeterministicGenerator` now records a real, measured `cost_usd: 0.0`** (Codex review pass 1,
HIGH-003) — it never calls an LLM, so this is a genuine, confident measurement, not a fabricated
default. `BenchmarkReport.cost_measured_count` (surfaced in the report payload and Markdown
rendering) reports how many cases actually had a cost measurement, so a run against a different,
real LLM-backed manifest — where nothing currently populates `Answer.metadata["cost_usd"]` (cost
lives on a `Trace`/`TraceStep` per ADR-0013, not on `Answer` itself) — shows `0/N measured`
rather than a misleading `avg_cost_usd: 0.0` indistinguishable from a genuine zero. Real LLM cost
propagation through the engine/result boundary remains a known limitation, not attempted here —
see "Explicitly out of scope" below.

## Retrieval and generation errors are distinguished, not lumped together

Every failed case gets `Metrics.error_stage` set to one of `"retrieval"` (a `RetrievalError`),
`"generation"` (`GenerationError`), `"security"` (an unexpected guard block on a normal `qa`
case), or `"infra"` (anything else) — `BenchmarkReport.error_stage_counts()` reports the
breakdown. An *expected* safety block (`case_type: safety`, `expect_block: true`, guard fired) is
**not** counted as a failure at all — it is the case behaving correctly, scored via
`safety_score`, not `error_stage`.

## Reproducibility

The golden set's corpus declares `Chunk`s directly, with fixed, author-chosen `chunk_id`/`doc_id`
values — not `Document`s to be chunked at load time. `Chunk.id`/`Document.id` both default to a
fresh random id per construction (`core/ids.py::new_id()`). Chunking a `Document` at load time
would produce a *different* random chunk id on every run, and `relevant_chunk_ids` would have
nothing stable to reference. See `eval/datasets/loader.py`'s own docstring.

The benchmark's own manifest (`src/modular_rag/eval/manifests/benchmark-deterministic.yaml`)
wires:
- `embedder: deterministic` / `generator: deterministic` — feature-hashed embeddings, extractive
  template generation. No model download, no API key, no network beyond the configured Qdrant.
- `retriever: hybrid` with the in-memory BM25 default (`lexical: bm25-memory`) — the same
  zero-network pattern `tests/e2e/test_secure_preset_e2e.py` already established for this
  codebase's deterministic e2e scenario.

**Collection state, not just corpus content, is now reproducible** (Codex review pass 1,
MEDIUM-002): `scripts/run_benchmark.py` clears the manifest's wired indexer
(`Indexer.clear()` — delete + recreate the collection) before every ingest, by default. Before
this fix, `index()`'s upsert-only semantics meant a stale point from a previous run — a corpus
entry since removed from `core_v1.yaml`, or a leftover from a different manifest that happened to
point at the same collection — could silently affect a local rerun's retrieval scoring; only a
fresh CI service container was actually clean. Pass `--no-clear-collection` to skip this (e.g. to
inspect a collection's state across runs); this is destructive to whatever the manifest's
`indexer.config.collection` currently holds.

**Golden-set schema validation** (Codex review pass 1, MEDIUM-001):
`eval/datasets/loader.py` now rejects a case with an invalid `case_type` (anything other than
`"qa"`/`"safety"`), a non-boolean `expect_block`, a malformed `relevant_chunk_ids` (not a
`list[str]`), or a `relevant_chunk_ids` entry that doesn't reference an id in the same file's
`corpus` — each of these used to load "successfully" while silently corrupting scoring (e.g. a
`case_type: saftey` typo scored as an ordinary QA case instead of a safety probe).

## Report format and comparing commits

`scripts/run_benchmark.py` writes two artifacts per run:

- `src/modular_rag/eval/reports/latest.json` — machine-readable, gitignored (regenerated every
  run; `git log` plus CI's uploaded `benchmark-report` artifact are the historical record, not git
  blame on this file).
- `src/modular_rag/eval/reports/latest.md` — the same payload rendered as a human-readable table,
  including a **delta column against the baseline** whenever one exists.

Both are keyed by the current git commit (`commit_sha`, best-effort — `None` outside a git
checkout) — the "comparison between commits" acceptance criterion: run the script on two commits,
diff their `latest.json`, or read either commit's CI-uploaded `benchmark-report` artifact.

## The quality gate and its documented thresholds

`src/modular_rag/eval/reports/baseline.json` is the checked-in reference `scripts/run_benchmark.py`
gates every run against, via `eval.quality_gate.QualityGate` — extended in this Batch with a
`lower_is_better` parameter so one gate instance enforces both "higher is better" quality metrics
(`quality_summary()`) and "lower is better" cost/latency metrics (`cost_summary()`) together.

**Current thresholds are a deliberately lenient, hand-authored floor, not a measured baseline** —
this sandbox has no live Qdrant to actually run the benchmark against (the same environmental
limitation recorded in every prior offline-observability handoff this session; see
`baseline.json`'s own `calibration_note` field). Two numbers *are* real, confident assertions
today, not placeholders:

| Metric | Baseline | Why this one is trustworthy without a real run |
|---|---|---|
| `safety_pass_rate` | `1.0` | `BasicSecurityGuard` is pure, exact regex matching — deterministic, not statistical. A regression here means a pattern genuinely broke. |
| `avg_cost_usd` | `0.0` | `DeterministicGenerator` explicitly records a real, measured `cost_usd=0.0` — never a fabricated default (see "What it measures" above). Any positive value is a real bug (e.g. a manifest accidentally wired to a real generator). |
| `failure_rate` | `0.0` | The golden set's 13 cases are all expected to run to completion — any failure is a real regression, not statistical noise. Gated via `cost_summary()`'s `lower_is_better` set (Codex review pass 1, HIGH-001): before this, a majority-failed run could still pass, since `_avg()` excludes every failed case from every other gated metric. |

Every other threshold (`avg_recall`, `avg_ndcg`, `avg_faithfulness`, `avg_answer_correctness`,
`avg_answer_relevance`, `avg_latency_ms`, `p95_latency_ms`) is set low/high enough to only catch a
*catastrophic* regression (retrieval or generation totally broken) until a maintainer runs the
real benchmark once and tightens it:

```bash
python scripts/run_benchmark.py --update-baseline
```

This overwrites `baseline.json` with the current run's actual measured numbers (still requires a
reachable Qdrant — see below). Re-run this whenever the golden set, the benchmark manifest, or a
deliberately-accepted quality change makes the old baseline stale; commit the updated file as its
own reviewable change, the same way `docs/observability/slo.md`'s thresholds are meant to be
revisited "once real traffic history exists."

## Running locally

```bash
# 1. Start Qdrant (any equivalent local install works too):
docker run -d -p 6333:6333 qdrant/qdrant

# 2. Report-only (never fails the command, prints violations if any):
python scripts/run_benchmark.py

# 3. Blocking mode (matches what CI runs — exits 1 on a regression):
python scripts/run_benchmark.py --enforce
```

## CI integration

`.github/workflows/ci.yml`'s `benchmark-gate` job runs `python scripts/run_benchmark.py --enforce`
against the same Qdrant service-container pattern `test-integration`/`e2e-deterministic` already
use (not a new CI service) and uploads `latest.json`/`latest.md` as a workflow artifact
(`if: always()` — the report is useful even when the gate fails). A significant regression past
`baseline.json` (tolerance `0.02` by default, `--tolerance` to override) fails the job.

## Explicitly out of scope for this Batch

- **LLM-as-judge metrics** (RAGAS/ARES/TRACe) — would need a real, paid, non-deterministic LLM
  call; deferred per this benchmark's own "reproducible, no LLM key" requirement. `faithfulness`/
  `answer_correctness` here are deterministic lexical proxies, documented as such above.
- **Stratified/per-cluster golden-set coverage**
  ([docs/research/DIGEST-evaluation.md](../research/DIGEST-evaluation.md) #2, `[2604.20763]`) — the
  task asked for "a small... golden dataset," not a corpus-coverage audit; a future Batch can add
  stratification once a real corpus (not 6 synthetic passages) exists to stratify.
  Non-anonymized/production-scale golden sets, a `/metrics`-style live dashboard for benchmark
  history, and per-tenant benchmark segmentation are likewise out of scope.
- **Real LLM-backed generators in CI** — the benchmark's default manifest is deterministic-only;
  running it against `openai`/`anthropic` locally (with a real key) works unchanged, since
  `BenchmarkRunner`/`scripts/run_benchmark.py` are engine-agnostic, but no CI job does this (no LLM
  secret is available to the main pipeline, per this repo's own established convention).
