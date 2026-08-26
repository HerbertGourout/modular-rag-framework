# Service Level Objectives (SLO)

ADR-0013 (`docs/adr/0013-operational-metrics-meter-port.md`), Lot 12 (external plan — "Metrics,
Dashboards, and SLO") — a minimum SLO set, per the task's own wording, not an exhaustive catalog.
`docs/refactoring-plan.md` §9's open-items table has explicitly listed "SLOs, throughput, corpus
scale, and cost budgets" as an unestablished gap ("performance gates cannot be set") since before
this Lot; this document is what closes that gap.

**Status: reference targets, not yet measured against real production traffic.** Every number
below is a starting point calibrated against what this codebase's own components are built to do
(e.g. `.claude/rules/health-checks.md`'s single-attempt, bounded-timeout probe discipline; the
generation providers' own per-call timeouts), not a number derived from observed production
percentiles — none exist yet, since this is the first Lot to expose the metrics an SLO needs.
Revisit every target here once real traffic history exists; treat premature over-precision as a
bigger risk than an honestly-approximate starting point.

## 1. Request availability

**Objective:** 99.5% of `answer` and `retrieve` operations that enter `ApplicationService`
complete without an exception, measured over a rolling 30-day window.

- **Metric:** `1 - (sum(rate(mrag_request_errors_total[30d])) / sum(rate(mrag_request_duration_ms_count[30d])))`, per `operation`.
- **Error budget:** 0.5% of requests over 30 days (~216 minutes of full-outage-equivalent budget,
  spread across however many partial-degradation minutes actually occur).
- **Alert:** `MRAGHighErrorRate` (`alerts.yaml`) is the fast-burn signal (5% over 5 minutes) — a
  much tighter window than the 30-day objective, deliberately, so an acute incident pages long
  before the monthly budget is meaningfully at risk.
- **Does not cover:** HTTP failures generated before `ApplicationService`, including 401, 413,
  request-validation 422, rate-limit 429 and concurrency-limit 503 responses. Security or policy
  exceptions raised inside the service are counted and can be separated with `error_type`; guard
  rejections that return a blocked answer are tracked by `mrag.guard.rejections` instead.

## 2. Request latency

**Objective:** p95 latency for `/answer` under 5 seconds; p95 latency for `/retrieve` under 1
second, measured over a rolling 7-day window.

- **Metric:** `histogram_quantile(0.95, sum(rate(mrag_request_duration_ms_bucket[7d])) by (le, operation))`.
- **Why `/answer` and `/retrieve` get different targets:** `/answer` includes a real LLM generation
  call (typically the dominant latency term); `/retrieve` never does.
- **Alert:** `MRAGHighP95Latency` (`alerts.yaml`), a faster 5-minute/10-minute window for
  acute-incident detection, same relationship as the availability SLO/alert pair above.
- **Known gap:** no per-stage latency SLO exists yet (retrieval-only vs. generation-only p95
  within an `/answer` call) — the per-stage `TraceStep.latency_ms` data already exists (ADR-0012)
  but isn't yet exported as its own histogram metric; a natural follow-up, not built in this Lot.
- **Boundary:** middleware time, including time waiting for the concurrency limiter, is not part of
  this histogram; it measures application-service execution only.

## 3. Retrieval quality (proxy)

**Objective:** Fewer than 5% of `/answer`/`/retrieve` requests return zero chunks, measured over a
rolling 24-hour window.

- **Metric:** `sum(rate(mrag_retrieve_empty_total[24h])) by (operation) / sum(rate(mrag_request_duration_ms_count[24h])) by (operation)`.
- **This is a proxy, not a true recall/precision SLO** — `RAGEngine.retrieve()`'s zero-chunk
  signal says nothing about whether the *non-empty* results were actually relevant. A real
  retrieval-quality SLO needs `eval/`'s golden-set-based `recall_at_k`/`precision_at_k` (V1.1,
  offline, not this Lot's live-metrics scope) — recorded here as an explicit known gap, not
  silently conflated with what this metric actually measures.
- **Alert:** `MRAGHighEmptyFetchRate`.

## 4. Degraded-mode target — not currently measurable

**Objective:** No more than 4 hours of cumulative `DEGRADED` readiness state per 30-day window;
zero tolerance (page immediately) for any `UNREADY` state.

- **Metric limitation:** `mrag.readiness.state` emits `1` for the observed labelled state but does
  not reset the other labelled states to `0`. After a process transitions from degraded/unready to
  healthy, the old series can remain `1`. The objective therefore cannot be measured reliably and
  no readiness-state alert is shipped in `alerts.yaml` yet.
- **Complementary per-request signal:** `mrag.retrieve.degraded` (per-request leg failure) is
  tracked separately (`MRAGRetrievalDegraded`) since a pod can be globally `HEALTHY`/`DEGRADED`
  while still occasionally losing one retrieval leg on individual requests — see ADR-0013 §7's
  explicit "these are two different questions" note.

## 5. Cost budget (reference, not an approved production limit)

**Objective (placeholder — replace with your organization's actual approved budget):** Daily
generation cost under $100/day, projected from a rolling 1-hour rate.

- **Metric:** `sum(rate(mrag_generation_cost_usd_total[1h])) * 24`.
- **Caveat:** `core/pricing.py`'s price table is a static, manually-refreshed approximation (see
  its own module docstring); this SLO is only as accurate as that table. Treat cost figures as
  directional, not invoice-grade, until a real billing reconciliation process exists.
- **Alert:** `MRAGCostBudgetExceeded` — the $100/day threshold in `alerts.yaml` is a placeholder
  and must be replaced with an actual approved figure before this alert is trusted in production.

## 6. Governance backlog — partially measurable

**Objective:** Human-review queue depth stays under 50 pending items; index-reconciliation
divergence count is zero at every scheduled `check()` run.

- **Metrics:** `mrag_review_pending`, `mrag_reconciliation_divergences`.
- `mrag.reconciliation.divergences` is reset for all four types on every explicit `check()` and
  supports `MRAGIndexDivergenceDetected`.
- `mrag.review.pending` is updated only when an item is enqueued, not when one is resolved. It can
  overstate the backlog, so the queue-depth objective is not currently enforceable and no
  `MRAGReviewQueueBacklog` rule is shipped.

## Explicitly not covered by this document

- Per-tenant SLOs (a noisy-neighbor tenant degrading another tenant's experience) — this
  framework's metrics carry no `tenant_id` label anywhere (deliberately — see ADR-0013 §4's
  cardinality-safety design; tenant count is not bounded/known in general, so it is treated the
  same as any other high-cardinality risk). A per-tenant SLO would need a separate, explicitly
  bounded tenant allowlist mechanism, not built here.
- Ingestion-pipeline SLOs (a target ingestion throughput or a maximum ingest-to-searchable
  latency) — `mrag.ingest.*` metrics exist (see the dashboard's ingestion panel) but no target has
  been set; add one once real ingestion-volume history exists.
- Anything requiring `eval/`'s offline, golden-set-dependent scorers (true recall/precision/NDCG,
  answer groundedness/faithfulness) — those live in a different, offline evaluation plane (ADR-0008)
  outside this Lot's live-metrics scope.
