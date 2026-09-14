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

**`DeterministicGenerator` records a real, measured `cost_usd: 0.0`**, and every safety-probe
branch does too — including a query blocked before generation ever ran (no generator, real or
deterministic, was invoked, so `0.0` is a genuine measurement there as well) — so a fully
successful run against the shipped deterministic manifest has 100% cost coverage
(`cost_measured_count == total_cases`), not a partial one (Codex review pass 1 HIGH-003, tightened
at pass 2 after a first attempt still left the three `expect_block: true` safety cases
uncovered).

`BenchmarkReport.cost_measured_count` (surfaced in the report payload and Markdown rendering)
reports how many cases actually had a cost measurement. Critically, **`avg_cost_usd` itself fails
closed to `math.inf` whenever `cost_measured_count` is `0`** (Codex review pass 2, HIGH-003) —
matching `QualityGate`'s own "missing lower-is-better metric is infinite, never zero" convention
— rather than the ambiguous `0.0` an earlier version of this fix left in place, which let a
zero-coverage run silently pass a `0.0` baseline. A run against a different, real LLM-backed
manifest — where nothing currently populates `Answer.metadata["cost_usd"]` outside the blocked-
pre-generation case (cost otherwise lives on a `Trace`/`TraceStep` per ADR-0013, not on `Answer`
itself) — now reports `avg_cost_usd: Infinity` and fails the gate, instead of a misleading
`avg_cost_usd: 0.0` indistinguishable from a genuine zero. Real LLM cost propagation through the
engine/result boundary remains a known limitation, not attempted here — see "Explicitly out of
scope" below.

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

**Collection state, not just corpus content, is reproducible for the shipped benchmark manifest**
(Codex review pass 1, MEDIUM-002). Before this, `index()`'s upsert-only semantics meant a stale
point from a previous run — a corpus entry since removed from `core_v1.yaml`, or a leftover from
a different manifest that happened to point at the same collection — could silently affect a
local rerun's retrieval scoring; only a fresh CI service container was actually clean.

`scripts/run_benchmark.py` now clears the wired indexer (`Indexer.clear()` — delete + recreate the
collection) before ingest, but **only when it can confirm the collection is benchmark-owned** —
gated by `_should_clear_collection()`, which checks the wired manifest's own `id` field against
`KNOWN_BENCHMARK_MANIFEST_ID` (`"eval-benchmark-deterministic"`, the shipped manifest's real id).
Running the script with its default `--manifest` therefore still gets a fully reproducible,
clean-state run automatically. Pointing `--manifest` at any other manifest leaves its collection
untouched unless you pass `--clear-collection` explicitly, having confirmed that collection is
safe to wipe — this flag is destructive (delete + recreate) to whatever that manifest's
`indexer.config.collection` currently holds. (Codex review pass 2, HIGH-004: an earlier version of
this fix cleared whichever `--manifest`'s collection was supplied, by default, with only an
opt-*out* flag — destructive against an arbitrary custom, shared, or production collection for
anyone running this against their own manifest, which this document's own "Real LLM-backed
generators" section below has always said works unchanged. The ownership check above closes that
gap; the flag is opt-*in* now, not opt-out.)

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
| `avg_cost_usd` | `0.0` | `DeterministicGenerator` and every safety-probe branch explicitly record a real, measured `cost_usd=0.0` — never a fabricated default (see "What it measures" above), and the golden set's own 13 cases reach 100% coverage under the shipped manifest. Any positive value is a real bug (e.g. a manifest accidentally wired to a real generator); a *missing* measurement now reports `Infinity` and fails the gate rather than a suspicious `0.0`. |
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

## Planned multi-engine assurance benchmark (Lots 21-22; not implemented)

The current Batch 13 benchmark answers a deliberately narrow question: did the shipped native
reference pipeline regress on a small deterministic golden set? It does **not** yet demonstrate
that the framework is portable across engines or that it reduces the work required to govern an
existing application. Those remain product hypotheses. The Lot 21 assurance contract they depend
on is now implemented and merged ([ADR-0017](../adr/0017-engine-independent-assurance-contract.md),
PR #8); what is still missing is the Lot 22 external-application pilot the paired comparison needs.

The future benchmark must answer three separate questions rather than collapse them into one
score:

1. **Quality:** for comparable inputs and resources, does adding the assurance layer preserve
   retrieval and answer quality within a pre-declared non-inferiority margin?
2. **Assurance:** does each integration enforce and evidence the controls it declares, including
   tenant isolation, egress decisions, audit completeness, and provenance?
3. **Portability and effort:** how much engine-specific work is required to obtain the same
   assurance outcome on another stack?

### Comparison design

Every external stack must be evaluated in a paired comparison: the application or engine with
its native controls, then the **same** application or engine behind the framework assurance
boundary. The native reference engine is evaluated as the executable reference for the
framework contracts, not presented as a neutral baseline for every vendor feature.

Two result tracks must remain separate:

| Track | What is held constant | Question answered |
|---|---|---|
| Controlled components | corpus snapshot, queries, embedding/generation models where possible, retrieval limits, policy inputs, and scoring | What overhead or behavior change is attributable to the framework boundary? |
| Stack-native optimized | each stack may use its normal recommended components and tuning; dataset and acceptance scenarios remain fixed | What outcome can a realistic implementation deliver, including its platform-specific work? |

The first comparison set is the native adapter, the current LangGraph adapter, and the existing
LangChain/LangGraph application selected by Lot 22. Additional frameworks or managed-cloud
engines are added only after that pilot proves that the protocol and normalized evidence are
useful. An unsupported capability is not counted as a failure when the adapter declares it
honestly; a capability that is declared but not honoured is a conformance failure.

### Dataset portfolio

Use a versioned portfolio rather than one aggregate leaderboard. Each imported snapshot must
record its source version, licence, checksum, transformation script, included subsets, and known
limitations. Public or sanitized data is required; real client data must not enter the repository
or shared benchmark artifacts.

The intended progression is:

- **Initial text-RAG qualification:** curated RAGBench subsets for retrieval, answer quality, and
  attribution; one financial/table task such as FinanceBench or TAT-QA; and one multi-hop task
  such as HotpotQA or MuSiQue.
- **Dynamic and graph-aware qualification:** CRAG or an equivalent snapshot only when a tested
  web/knowledge-graph retrieval path exists. Until then it is a future candidate, not evidence
  for V3 GraphRAG support.
- **Multilingual and multimodal qualification:** Open RAG Benchmark, ViDoRe, Double-Bench, or
  equivalent datasets only when the corresponding V5 ingestion, retrieval, and evidence paths
  exist. Text-only adapters must not be penalized for capabilities they do not claim.

Scores must be stratified by dataset, domain, question type, hop count, evidence modality,
language, and relevant capability where labels permit. Empty or underrepresented strata must be
reported instead of being hidden by a global average, following
[DIGEST-evaluation.md](../research/DIGEST-evaluation.md)'s coverage guidance.

### Assurance scenario corpus

Public QA datasets do not test the framework's main product hypothesis by themselves. A separate,
deterministic assurance corpus must run the same scenarios against every compatible integration:

- normal request and citation/provenance verification;
- tenant A attempting to retrieve tenant B's content;
- prompt injection or poisoned instructions embedded in a document;
- PII, secrets, restricted classification, and denied provider egress;
- low-confidence evidence requiring abstention or review;
- provider error, timeout, retry, cancellation, and partial failure;
- document update/deletion and proof that stale evidence is no longer returned;
- model/provider change and a deliberately introduced quality regression;
- streaming or tool execution attempting to bypass a declared prevalidation control.

Each scenario needs an expected policy outcome and expected evidence, not merely an expected final
answer. Lot 21's `ConformanceReport` is the normalized source for what was observed, verified, or
enforced; vendor traces may supplement it but cannot silently upgrade an assurance claim.

### Metrics and evidence

The comparison report must keep these metric families separate:

| Family | Minimum evidence |
|---|---|
| RAG quality | recall/precision/MRR/NDCG, answer correctness, faithfulness, citation precision/recall, abstention accuracy, results per stratum |
| Governance | correct block/allow rate, cross-tenant leaks, forbidden egress calls, mandatory audit-field completeness, provenance coverage, false positives/negatives, achieved assurance level |
| Portability | conformance checks passed by adapter and capability, framework-owned reusable assets versus engine-specific assets, manifest/policy reuse rate |
| Integration effort | person-hours, elapsed time for defined tasks, application lines changed, configuration and test files added, engine-specific code, and required specialist interventions |
| Operations | framework-added latency, end-to-end latency, token/cost coverage, failure recovery, incident reproduction time, and change-of-provider time |

Integration effort must be measured from predefined tasks -- for example add one policy, switch
provider, reproduce one incident, and produce one conformance report -- with start/end rules and
reviewable change evidence. A subjective estimate after implementation is not sufficient.

Every run must record the dataset snapshot, engine and adapter versions, model and embedding
versions, manifest and policy hashes, random seed, environment, resource limits, timestamps,
cold/warm state, repetition count, and missing measurements. Provider latency and model cost must
be reported separately from framework-added overhead. Failed or absent measurements remain
explicit and must never be coerced to zero.

### Gates and interpretation

Thresholds are calibrated from pilot evidence before they become blocking CI gates. The initial
hard invariants are qualitative: zero cross-tenant leakage, zero forbidden outbound call, no
content before a required streaming approval, and complete mandatory conformance evidence. Quality
non-inferiority margins, acceptable latency overhead, and the target reduction in integration
effort must be proposed from repeated runs and approved as versioned baselines; this document does
not invent those numbers in advance.

The resulting matrix supports a defensible statement of the form: *for comparable RAG quality,
the framework delivered these verified controls with this measured amount of reusable and
engine-specific work*. It must not be converted into a generic claim that the framework has
better orchestration, connectors, models, or cloud-native features than the underlying stacks.

Lot 21 owns the status-aware conformance contract and real-adapter suite
(`tests/contract/test_engine_conformance.py`). Lot 22 owns the
paired existing-application pilot, effort measurement, and continue/stop decision. This guide is
the shared evaluation protocol; it does not change either lot's dependency gate.

## Explicitly out of scope for this Batch

- **LLM-as-judge metrics** (RAGAS/ARES/TRACe) — would need a real, paid, non-deterministic LLM
  call; deferred per this benchmark's own "reproducible, no LLM key" requirement. `faithfulness`/
  `answer_correctness` here are deterministic lexical proxies, documented as such above.
- **Stratified/per-cluster golden-set coverage**
  ([docs/research/DIGEST-evaluation.md](../research/DIGEST-evaluation.md) #2, `[2604.20763]`) — the
  task asked for "a small... golden dataset," not a corpus-coverage audit; a future Batch can add
  stratification once a real corpus (not 6 synthetic passages) exists to stratify. The planned
  multi-engine protocol above requires this later; the current script does not implement it.
  Non-anonymized/production-scale golden sets, a `/metrics`-style live dashboard for benchmark
  history, and per-tenant benchmark segmentation are likewise out of scope.
- **Real LLM-backed generators in CI** — the benchmark's default manifest is deterministic-only;
  running it against `openai`/`anthropic` locally (with a real key) works unchanged, since
  `BenchmarkRunner`/`scripts/run_benchmark.py` are engine-agnostic, but no CI job does this (no LLM
  secret is available to the main pipeline, per this repo's own established convention).
