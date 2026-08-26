# Observability Reference Material

ADR-0013 (`docs/adr/0013-operational-metrics-meter-port.md`), Lot 12 (external plan — "Metrics,
Dashboards, and SLO"). For the *code-level* API (the `Meter` Protocol, the metric catalog, how to
wire `observability.meter` in a manifest, cardinality safety), see
[docs/guides/observability.md](../guides/observability.md)'s "Operational metrics (Meter)"
section — this directory holds the *operational* deliverables that section links out to:

| File | What it is |
|---|---|
| [dashboard.json](dashboard.json) | A reference Grafana dashboard (12 panels, RED method + cost/degradation/reconciliation/review) |
| [alerts.yaml](alerts.yaml) | A minimum set of Prometheus/Alertmanager alerting rules, each linked to a runbook section |
| [slo.md](slo.md) | Service Level Objectives the alerts above protect, with explicit "not yet measured against real traffic" caveats |
| [runbooks.md](runbooks.md) | One runbook section per alert — what it means, what to check, what to do, what not to do |

No shipped preset enables `observability.meter`; these artifacts become relevant only after a
custom manifest selects `meter.type: otel` and an exporter/backend is configured.

## Known instrumentation boundaries

- Request duration/error series start inside `ApplicationService`. HTTP failures produced before
  that boundary (authentication, payload/validation rejection, rate limiting and concurrency
  limiting) are not counted.
- `mrag.readiness.state` currently sets only the observed labelled state to `1`; previous state
  series are not reset. It cannot reliably prove recovery and is dashboard-only for now.
- `mrag.review.pending` is sampled on enqueue and is not refreshed when an item is resolved. It is
  not an authoritative queue-depth signal.

For those reasons, the reference alert file intentionally contains no readiness-state or
review-backlog rule. Add them only after the corresponding emission semantics are corrected and
verified against a real backend.

## Important caveat: none of this was validated against live infrastructure

This Lot was implemented in a sandboxed development environment with no live Prometheus, Grafana,
Alertmanager, or OTel Collector available. Every file above is:

- **Structurally valid** — `dashboard.json` is confirmed valid JSON, `alerts.yaml` is confirmed
  valid YAML, both checked directly (not assumed) before being committed.
- **Consistent with the actual metric names, types, and labels this codebase's `OtelMeter`
  emits** — the full catalog is documented in `docs/guides/observability.md` and was cross-checked
  against every real emission call site in `orchestration/engine.py`/`reconciliation.py`/
  `app/application.py`/`api/__init__.py`, not invented independently of the implementation.
- **Not confirmed to render/fire correctly against a real Grafana/Prometheus/Alertmanager
  deployment.** The PromQL queries and Grafana panel JSON assume metric names have gone through
  the standard OTel-to-Prometheus naming conversion (dots → underscores, histogram
  `_bucket`/`_sum`/`_count` suffixes, counter `_total` suffix) that an OTel Collector's Prometheus
  exporter applies — if your actual collector/backend renders names differently, every query in
  `dashboard.json`/`alerts.yaml` needs the equivalent substitution.

Treat this directory as a carefully-reasoned starting point to import and adapt against your real
metrics backend, not a guaranteed drop-in — the same honesty standard this project's own
`docs/guides/backup-restore.md` (Lot 16c) already established for operational runbooks whose
procedures also couldn't be executed against real infrastructure inside this development
environment.

## Metric-name conversion reference

| This codebase emits (via `Meter`) | Type | Typical Prometheus-exported name |
|---|---|---|
| `mrag.request.duration_ms` | histogram | `mrag_request_duration_ms_bucket` / `_sum` / `_count` |
| `mrag.request.errors` | counter | `mrag_request_errors_total` |
| `mrag.ingest.documents` | counter | `mrag_ingest_documents_total` |
| `mrag.ingest.chunks` | counter | `mrag_ingest_chunks_total` |
| `mrag.ingest.duration_ms` | histogram | `mrag_ingest_duration_ms_bucket` / `_sum` / `_count` |
| `mrag.ingest.errors` | counter | `mrag_ingest_errors_total` |
| `mrag.guard.rejections` | counter | `mrag_guard_rejections_total` |
| `mrag.retrieve.empty` | counter | `mrag_retrieve_empty_total` |
| `mrag.retrieve.degraded` | counter | `mrag_retrieve_degraded_total` |
| `mrag.readiness.state` | gauge | `mrag_readiness_state` |
| `mrag.generation.tokens` | counter | `mrag_generation_tokens_total` |
| `mrag.generation.cost_usd` | counter | `mrag_generation_cost_usd_total` |
| `mrag.reconciliation.divergences` | gauge | `mrag_reconciliation_divergences` |
| `mrag.review.enqueued` | counter | `mrag_review_enqueued_total` |
| `mrag.review.pending` | gauge | `mrag_review_pending` |

If you export via a different path (a vendor's own OTLP-native backend — Honeycomb, Grafana Mimir
in native OTLP mode, etc.) the original dotted names are typically preserved as-is; adapt
`dashboard.json`/`alerts.yaml`'s queries to that backend's own query language instead of PromQL.
