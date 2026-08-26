# ADR-0013 — Operational Metrics via a New `Meter` Port

**Status:** Accepted
**Date:** 2026-08-25
**Authors:** Claude Code (implementation), reviewed via the project's Codex handoff process

---

## Context

Lot 12 (external plan — "Metrics, Dashboards, and SLO"; **not** this repository's own
`docs/refactoring-plan.md` Lot numbering — see the numbering-collision convention established in
earlier external-plan Lots) asks for operational SRE-style metrics — latency, errors, rejections,
empty-fetch, degradation, tokens, cost, ingestion, index discrepancy, and human review — exposed
as collectable counters/histograms/gauges (`/metrics` or OTLP metrics export), with bounded label
cardinality, a reference dashboard, minimum alerts/SLOs, and runbooks.

This builds directly on Lot 11/ADR-0012 (`Tracer`/`Span`, live distributed-tracing spans), which
already wired `opentelemetry-sdk`/`opentelemetry-api`/`opentelemetry-exporter-otlp` (the `v4`
extras group) into this codebase for the first time. Metrics are OpenTelemetry's *other* signal
type — counters/histograms/gauges, not spans — and the same SDK package already provides a full
`opentelemetry.sdk.metrics` API (confirmed directly: `MeterProvider.create_counter()`/
`create_histogram()`/`create_gauge()` all work with the already-installed `opentelemetry-sdk
1.44.0`, well above the `>=1.24` pin) and OTLP metrics export
(`opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter`, bundled in the same
`opentelemetry-exporter-otlp` meta-package ADR-0012 already declared) — **no new dependency is
required**.

Two existing mechanisms are easy to confuse with what this ADR adds, and are deliberately left
untouched:
- **`core.models.metrics.Metrics`** (`contracts/telemetry.py`'s `Telemetry.record_metrics()`) is a
  post-hoc, per-run **evaluation-quality** bag (recall/precision/NDCG/groundedness/policy
  violations/cost_usd/latency_ms — 16 fields, one scalar snapshot per completed run, never called
  anywhere on the live request path today — confirmed by grep: zero callers of `record_metrics()`
  in `src/` besides the Protocol declaration and its two `Telemetry` implementers). It has no
  notion of continuous aggregation, labels, or export to a metrics backend.
- **`Tracer`/`Span`** (ADR-0012) are live distributed-tracing spans — one span per operation,
  discarded after export, with unbounded-cardinality attributes safe by design (a span attribute
  never becomes a persistent time series).

Neither can safely or correctly serve as "collectable operational metrics with bounded
cardinality" — hence a new, third mechanism, and a new name (`Meter`, not `Metrics`) to avoid
colliding with the already-taken `core.models.metrics.Metrics`.

`docs/research/`'s curated arXiv digests have **no coverage** of SRE metrics design — cardinality
safety, RED/USE-method dashboards, alerting discipline, or SLO definitions are established
industry/operational practice (Prometheus's and OpenTelemetry's own documentation, the Google SRE
book's RED/USE framing), not a research topic those digests were ever meant to cover. Per this
project's own citation discipline (`CLAUDE.md` §05 item 8: "a choice that contradicts the digest
must be justified explicitly"), this is recorded as an explicit non-citation rather than a
fabricated one: this ADR's cardinality-safety and dashboard/alert design follow established
community practice, not a project-internal research citation.

## Decision

1. **A new, additive Protocol** in `contracts/meter.py`: `Meter` (no separate "Instrument"
   Protocol — unlike OTel's own create-once-then-record-many-times object model, `Meter.counter()`/
   `.histogram()`/`.gauge()` are each one atomic "record now" call; `OtelMeter` caches the
   underlying OTel instrument objects internally so callers never manage that lifecycle). Mirrors
   `Tracer`'s shape and is a new contract, not a modification of `Telemetry` or `core.models.
   metrics.Metrics` — per `contracts/CLAUDE.md`'s "New Protocol in new version" precedent, this
   needs no migration of any existing implementer.

2. **`NullMeter`** (`observability/__init__.py`, alongside `NullTelemetry`/`NullTracer`) is the
   true no-op implementation — `observability.meter` omitted from a manifest (or explicitly
   `type: null`) means zero metrics are ever recorded, satisfying "instrumentation can be
   disabled" identically to how `tracer`/`telemetry` already do.

3. **`OtelMeter`** (`adapters/observability/otel_meter.py`) is the real implementation, structured
   as closely as possible to `OtelTracer` (ADR-0012) for consistency: lazy-imports every
   `opentelemetry.*` symbol inside method bodies only; `otlp_endpoint=None` (default) still builds
   real instruments and records real values (every attribute-setting code path exercised
   identically in every environment) but attaches no exporter, so nothing is ever transmitted
   ("toggleable export": the toggle is whether an endpoint is configured); setting `otlp_endpoint`
   attaches a `PeriodicExportingMetricReader(OTLPMetricExporter(...))`, which exports
   asynchronously on its own schedule and swallows/logs export failures internally — this, not any
   code in this adapter, is what satisfies "no functional impact if the exporter is unavailable."
   `OtelMeter.for_testing()` wires an in-process `InMemoryMetricReader` — the "test using an
   in-memory exporter" requirement, mirroring `OtelTracer.for_testing()`'s `InMemorySpanExporter`.

   **A real concurrency bug was found and fixed during this ADR's own implementation, before any
   external review**: an early version of `OtelMeter._get_instrument()` acquired its
   `threading.Lock` and then called `self._get_meter()` *from inside* that critical section;
   `_get_meter()` acquires the *same* lock internally. `threading.Lock` is not reentrant, so the
   very first `counter()`/`histogram()`/`gauge()` call against a freshly-constructed `OtelMeter()`
   (not `.for_testing()`, which pre-populates `_meter` and never takes this path) deadlocked
   permanently. Caught by this ADR's own test suite hanging (`test_disabled_export_still_creates_
   instruments_but_transmits_nothing`), not by a review round — fixed by calling `_get_meter()`
   *before* acquiring `_build_lock`, never from within it. Recorded here as the Lot 12 analog of
   ADR-0012's own MEDIUM-002 (a similar double-checked-locking race in `OtelTracer`), but caught
   one level earlier this time.

4. **Cardinality safety is enforced in code, not only documented.** `OtelMeter._sanitize_
   attributes()` runs on every `counter()`/`histogram()`/`gauge()` call and drops (never raises,
   logs a `structlog` warning instead) any attribute whose **key** matches a small denylist
   (`correlation_id`, `request_id`, `trace_id`, `span_id`, `query_id`, `chunk_id`, `document_id`,
   `doc_id`, `document_key`, `answer_id` — case-insensitive) or whose **value** is shaped like a
   UUID or ULID (catching an identifier under a key this denylist didn't anticipate). This is
   explicit defense in depth, not the primary safety mechanism — the primary mechanism is that no
   first-party call site in this codebase passes one of those values as a label (verified directly
   by writing and reviewing every emission site in `orchestration/engine.py`/`reconciliation.py`/
   `app/application.py`/`api/__init__.py`, the same discipline ADR-0012 §9 already applies to span
   attributes). Unlike a `Tracer`/`Span` attribute (safe at any cardinality — one value per span,
   discarded after export), a `Meter` label creates one persistent time series per distinct value
   combination in a real backend (Prometheus, OTLP), so an unbounded value here is a production
   incident, not a style nit — this asymmetry is why `Tracer`/`Span` needed no equivalent runtime
   check and `Meter` does.

5. **`Container.meter` follows the established `X | None` + `.get()` optional-role pattern**,
   identically to `Container.tracer`'s own ADR-0012 §5 rationale (not repeated here in full) —
   the nine-plus existing precedents for this pattern have zero recorded incidents, and
   introducing a fourth container-property convention was rejected for the same reason ADR-0012
   already rejected a third.

6. **Request-level RED metrics (`mrag.request.duration_ms`, `mrag.request.errors`) are recorded
   *only* at `app/application.py`'s `ApplicationService.answer()`/`.retrieve()`, never inside
   `RAGEngine._run()`/`.retrieve()`.** This is the one point where this ADR's design deliberately
   diverges from a naive "instrument everywhere a span already exists" approach, for two reasons:
   - `ApplicationService` is the actual common entry point for both the CLI (`load_application()`
     → `ApplicationService`, confirmed directly in `cli/*.py`) and the REST API
     (`api/__init__.py`'s `create_app()`), so recording there covers both callers uniformly.
   - It is **engine-neutral**: `ApplicationService.answer()` dispatches through the selected
     `DocumentEngine` (native or LangGraph), so recording at this boundary counts a request exactly
     once regardless of which engine served it — a LangGraph-routed request, which never calls
     into `RAGEngine` at all, is still counted; a native-engine request is counted exactly once,
     not twice.

   **A real double-counting bug from exactly this class of mistake was found and fixed during
   this ADR's own implementation**, before any external review: an early version additionally
   emitted `mrag.request.errors` inside `RAGEngine.retrieve()`'s own exception handler. Since
   `ApplicationService.retrieve()` (the standard path) calls straight into `RAGEngine.retrieve()`,
   a single failed request through the standard path would have incremented the counter *twice* —
   once at each layer — while a direct, ApplicationService-bypassing caller of `RAGEngine.
   retrieve()` would only increment it once, silently skewing the metric's meaning depending on
   which entry point a caller happened to use. Caught by writing `tests/unit/orchestration/
   test_engine.py::test_retrieve_does_not_emit_request_errors_counter_on_failure` while
   self-reviewing the corrective diff (this project's task-standard "self-review the complete task
   diff" step, applied literally), not by a review round. Fixed by removing the emission from
   `RAGEngine.retrieve()` entirely — that method still emits its own, non-duplicated
   `mrag.retrieve.empty`/`mrag.retrieve.degraded` counters, which have no equivalent at the
   `ApplicationService` layer and so carry no double-counting risk.

7. **Pipeline-stage metrics live in `orchestration/engine.py`/`orchestration/reconciliation.py`**,
   at the same call sites ADR-0012 already instruments with spans — mirroring that ADR's own
   "instrument the call sites of ingestion/retrieval/reranking/generation from the orchestration
   layer, never inside the domain module itself" decision exactly, for the same domain-independence
   reason. Concretely:

   | Category (task's own list) | Metric(s) | Where |
   |---|---|---|
   | Latency | `mrag.request.duration_ms` (histogram) | `ApplicationService.answer()`/`.retrieve()` |
   | Errors | `mrag.request.errors` (counter) | `ApplicationService.answer()`/`.retrieve()` |
   | Errors (ingest-specific) | `mrag.ingest.errors` (counter) | `RAGEngine.ingest_chunks()` |
   | Rejections | `mrag.guard.rejections` (counter, `stage`) | `RAGEngine._run_steps()` (query + answer guard) |
   | Empty fetch | `mrag.retrieve.empty` (counter, `operation`) | `RAGEngine._run_steps()`/`.retrieve()` |
   | Degradation (per-request) | `mrag.retrieve.degraded` (counter, `source`) | same, reading `HybridRetriever.last_degraded_sources` |
   | Degradation (whole-process) | `mrag.readiness.state` (gauge, `state`) | `GET /ready` (`api/__init__.py`), reading `check_readiness()` |
   | Tokens | `mrag.generation.tokens` (counter, `direction`, `model`) | `RAGEngine._run_steps()`, reading the generator's own `TraceStep` |
   | Cost | `mrag.generation.cost_usd` (counter, `model`) | same, reading `TraceStep.metadata["cost_usd"]` |
   | Ingestion | `mrag.ingest.documents`/`.chunks` (counters), `.duration_ms` (histogram) | `RAGEngine.ingest()`/`.ingest_chunks()` |
   | Index discrepancy | `mrag.reconciliation.divergences` (gauge, `type`) | `IndexReconciler.check()` |
   | Human review | `mrag.review.enqueued` (counter), `.pending` (gauge) | `RAGEngine._run_steps()` |

   Two whole-process/per-request signal pairs are **deliberately two separate metrics, not one**:
   `mrag.readiness.state` (sampled once per `/ready` poll) is intended to answer whole-process
   health, while `mrag.retrieve.degraded` answers whether a request lost a retrieval leg. Current
   readiness emission sets only the observed labelled state to `1` and does not reset the others,
   so an old state can remain visible after recovery. The metric is diagnostic until that emission
   semantic is corrected; it cannot yet safely answer "healthy right now" by itself.

8. **Cost is computed by a new, from-scratch, static price table** (`core/pricing.py`), not a live
   provider pricing-API lookup (would add network I/O and a new external dependency to the
   generation hot path, contradicting this codebase's lazy-import/cheap-instrumentation posture) —
   `Metrics.cost_usd` (the evaluation-quality field) has existed as a schema field since early on
   but was never once computed anywhere before this ADR; confirmed by grep before starting. The
   table's model coverage was checked directly against `generation/synthesizers/openai_gen.py`'s/
   `anthropic_gen.py`'s own default `model` values and every `model:` reference across
   `manifests/presets/`/`manifests/blueprints/`, rather than assumed — `tests/unit/core/
   test_pricing.py` cross-checks this so the table can't silently drift out of sync with what
   production traffic actually asks it to price. `estimate_cost_usd()` returns `None` (never a
   fabricated `0.0`) for a model outside the table; the two generators only attach `cost_usd` to
   their `TraceStep` metadata when it is not `None`, and `RAGEngine` only emits the
   `mrag.generation.cost_usd` counter when that key is present — an unpriced model still gets
   accurate token counters, just no cost figure.

9. **`ObservabilitySection.meter: ComponentConfig | None = None`** is added to
   `contracts/manifests.py`, identically to ADR-0012 §7's `tracer` field addition (a `BaseModel`
   addition, not a `Protocol` change, backward compatible with every existing manifest).

10. **`engine.adapter: "langgraph"` manifests that also set `observability.meter` are accepted at
    `wire()` time from the start** — applying ADR-0012 §8's correction (Codex pass-1 HIGH-001,
    where `tracer` was initially, incorrectly rejected under LangGraph) proactively this time,
    rather than needing a second corrective round to reach the same conclusion.
    `Container.meter` is read directly by `ApplicationService`'s engine-neutral RED-metric
    recording (decision 6 above), exactly the same reason `Container.tracer` is never silently
    ignored under LangGraph.

11. **PII safety**: metric labels are restricted to the same allowlist-style categories ADR-0012 §9
    already establishes for span attributes (operation names, stage/status/source names, bounded
    provider/model identifiers, bounded exception-class names) — with the additional, code-enforced
    cardinality check from decision 4 above, since a metric label carries a stricter safety
    requirement than a span attribute.

## Explicitly out of scope for this ADR

- **A live `/metrics` HTTP endpoint.** The task's own acceptance criterion is "expose `/metrics`
  **or** use the OTLP metrics export" (either, not both) — `OtelMeter`'s OTLP export path already
  satisfies "collectable metrics" without adding a new, unauthenticated HTTP route and a new
  Prometheus-text-format serialization dependency (`prometheus_client`) this task does not
  explicitly require. A `/metrics` Prometheus-scrape endpoint remains a legitimate, separately-
  scoped future addition (the reference dashboard/alerts below are written against metric *names*
  and *labels*, not against either specific transport, so they transfer to a future `/metrics`
  endpoint without modification).
- **`mrag.request.duration_ms`/`.errors` inside `RAGEngine._run()`/`.retrieve()`.** Deliberately
  not duplicated — see decision 6's double-counting discussion.
- **Telemetry/audit parity for `RAGEngine.retrieve()`'s internal `Trace`** (added by the HIGH-002
  corrective round of Lot 11/ADR-0012's own review cycle). That `Trace` is not recorded via
  `Telemetry`/`AuditSink`; extending it to be would be a separate, larger scope decision this Lot
  does not touch.
- **A periodic background sampler for `mrag.review.pending`/readiness.** Both are recorded
  request/poll-driven (on `enqueue()`, on `/ready`), not on a fixed interval. Review resolution
  does not refresh the pending gauge, so it may retain an obsolete high-water sample. This codebase has no
  scheduler component (confirmed: `CLAUDE.md`'s own "V1 has no scheduler component" note), and
  adding one is out of this Lot's scope.
- **`LangGraphEngineAdapter` internal step metrics**, mirroring ADR-0012's identical exclusion for
  spans — generic orchestration mechanics inside the external engine remain out of scope per
  ADR-0005 §5.2.
- **A live LLM-provider pricing API.** See decision 8 — a static table is the deliberate choice,
  not a stopgap.

## Consequences

**Positive:**
- Every metric the task names is now collectable, either via OTLP export or (with `console_export`
  during local development) to stdout, using zero new dependencies.
- Cardinality safety is a real, tested runtime property of `OtelMeter`, not only a documentation
  promise — a future call site that accidentally passes an unbounded label value is caught (and
  the metric emission still succeeds, safely, with that one label dropped) rather than silently
  corrupting a production metrics backend.
- Two real defects (a self-deadlock, a double-counted error metric) were found and fixed via this
  ADR's own test-writing and self-review discipline before any external review round — recorded
  here so the same class of mistake isn't repeated in a future Lot that follows this one as a
  template.

**Negative / accepted risk:**
- `core/pricing.py`'s price table is static and will drift from real provider pricing over time;
  its own module docstring documents the refresh expectation. One entry (`claude-opus-4-7`) has no
  public rate card at all and uses an explicitly-flagged placeholder extrapolation.
- No `/metrics` HTTP endpoint exists yet — a caller wanting Prometheus-native scraping (rather than
  OTLP push) must add one separately; the metric catalog above is written to transfer to it
  unchanged when that happens.
- `mrag.review.pending` is not refreshed on resolution, and `mrag.readiness.state` does not zero
  previously observed labelled states. The reference alert set therefore omits backlog/readiness
  alerts until those semantics are fixed; see `docs/observability/README.md`.
- Request RED metrics cover calls that enter `ApplicationService`, not HTTP errors produced first
  by authentication, request parsing/validation, rate limiting, body-size or concurrency middleware.

## References

- [ADR-0012](0012-opentelemetry-tracing-port.md) — the `Tracer`/`Span` port this ADR's `Meter` port
  mirrors structurally; most of this ADR's precedent-following decisions cite that ADR's own
  rationale rather than repeating it.
- [docs/refactoring-plan.md](../refactoring-plan.md) §9 (open items table) — "SLOs, throughput,
  corpus scale, and cost budgets... before Lot 13/14 blocking gates" — this ADR is what closes that
  gap for SLOs/cost specifically.
- [docs/observability/](../observability/) — the reference dashboard, alerts, SLOs, and runbooks
  this ADR's metric catalog backs.
- [.claude/rules/health-checks.md](../../.claude/rules/health-checks.md) — the "don't repeat a
  solved concurrency/asymmetry problem" precedent this ADR's own §3/§5 explicitly follow.
