# Feedback, human review, and drift detection

Batch 14 (external plan — "Feedback, drift, and human review"; ADR-0014). See
[ADR-0014](../adr/0014-feedback-drift-and-human-review.md) for the full design context and
[ADR-0008](../adr/0008-offline-evaluation-and-engine-activation.md) for the offline/non-blocking
constraint drift detection follows.

---

## What this adds

- A `Feedback` contract (`contracts/feedback.py`) and an authenticated `POST /feedback` endpoint.
- Durable Postgres backends for feedback (`PostgresFeedbackSink`) and human review
  (`PostgresReviewQueue`), alongside the existing in-memory reference implementations.
- Retention/purge CLI commands (`mrag feedback ...`, `mrag review ...`), mirroring `mrag audit`.
- An offline, script-driven drift-detection module (`eval/drift_detection.py`) and companion
  script (`scripts/run_drift_check.py`).

None of this is manifest-activated evaluation — per ADR-0008, only the *storage* of feedback and
review records is an online governance component (like `audit_sink`). Drift computation itself
stays offline, exactly like `scripts/run_benchmark.py`.

## Submitting feedback

```bash
curl -s -X POST http://localhost:8000/feedback \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <token>" \
     -d '{
           "trace_id": "a1b2c3d4",
           "rating": "thumbs_down",
           "correction_text": "The refund window is actually 30 days, not 14.",
           "citation_count": 2,
           "idempotency_key": "feedback-2026-08-28-001"
         }'
```

- **`trace_id` is required** — it is the only identifier this framework returns to a caller
  today (`AnswerResponse.trace_id`), so it is the only usable link back to the answer a piece of
  feedback concerns.
- **`idempotency_key` is required, non-blank, and scoped per tenant** — a retried submission with
  the same key for the same tenant is a silent no-op, not an error, and the response's `id`
  always identifies the record actually stored (the *first* successful submission's id, even on
  a retry — Codex review pass 1, MEDIUM-001). Generate one per logical feedback action (e.g. once
  per thumbs-down click), not per HTTP retry attempt.
- **`trace_id` must be non-blank and `citation_count`, if given, must be `>= 0`** — a request that
  violates either is rejected with HTTP 422, not silently persisted (Codex review pass 1,
  MEDIUM-002).
- **`citation_count`** is optional and caller-reported — the caller (a frontend rendering a
  feedback widget next to an answer) already has the answer's citation list. It powers the
  empty-retrieval drift signal below without any new backend telemetry.
- **`correction_text` requires a wired redactor.** `POST /feedback` returns an error
  (`ConfigurationError`, mapped to HTTP 502 like every other configuration error) if the pipeline
  has no `governance.redactor` configured — wiring one *is* the explicit sensitive-content policy
  this framework requires before storing any free-text feedback content. When a redactor is
  configured, `correction_text` is redacted (`PatternRedactor`, the same destructive redaction
  `/answer` already applies) before the `Feedback` object is ever constructed.
- **`is_test: true`** requires the caller's verified identity to carry the `"tester"` role
  (`TenantContext.roles`) — otherwise the request is rejected with `SecurityError` (HTTP 403).
  Test/QA feedback is excluded from every drift aggregation by default.

## Manifest activation

```yaml
governance:
  redactor:
    type: patterns
  feedback_sink:
    type: postgres          # or "in-memory" for local/dev
    config:
      dsn: "secret://AUDIT_DATABASE_URL"
  review_queue:
    type: postgres-human-review   # or "human-review" for the in-memory reference implementation
    config:
      dsn: "secret://AUDIT_DATABASE_URL"
      threshold: 0.7
```

See `manifests/presets/secure-enterprise-rag.yaml` for the full, real, runnable example. Neither
`feedback_sink` nor `review_queue` is consumed by `engine.adapter: langgraph` — same ADR-0008
boundary that already applies to `audit_sink`: `LangGraphEngineAdapter` never calls into
`RAGEngine.record_feedback()`, since it never calls into `RAGEngine` at all.

## Durable storage

`PostgresFeedbackSink`/`PostgresReviewQueue` (`adapters/feedback/`, `adapters/review/`) mirror
`PostgresAuditSink` exactly: connection pooling, circuit-breaker/retry classification, the same
`check_health()` invariants (`.claude/rules/health-checks.md`), and the same
retention/`purge_expired()` design (`AuditEvent.retention_days`'s own 365-day default, same
fail-closed `allow_purge` gate). Migrations `0005_feedback`/`0006_review_items`
(`adapters/postgres/sql/`) follow the exact numbering/`.up`/`.down` convention
`adapters/postgres/migrations.py` already enforces — apply with `mrag db migrate`.

`docs/guides/postgres-permissions.md` documents the two new tables' `GRANT` lines — `feedback` is
append-only (no `UPDATE`/`DELETE` for the application role, same as `audit_events`);
`review_items` is the one mutable table (`PostgresReviewQueue.resolve()` issues a real `UPDATE`),
so its application role also gets `UPDATE`, same as `document_lifecycle`.

## Operating on feedback and review records

```bash
# Retention (mirrors `mrag audit count-expired`/`purge` exactly):
mrag feedback count-expired --dsn <app-or-retention-role-dsn>
mrag feedback purge --dsn <retention-role-dsn>   # irreversible

mrag review count-expired --dsn <app-or-retention-role-dsn>
mrag review purge --dsn <retention-role-dsn>     # irreversible, resolved or not

# Human review (a CLI operation, not a public REST endpoint — the same
# DSN-based trust model every other administrative command in this codebase
# already uses, per docs/architecture/security.md):
mrag review list-pending --dsn <app-role-dsn>
mrag review resolve --item-id <id> --approved --reviewer alice --dsn <app-role-dsn>
```

`resolve()` is a terminal, compare-and-set transition on both `ReviewQueue` implementations
(Codex review pass 1, HIGH-002): resolving an already-resolved item raises the same "No pending
review item" error as resolving an unknown one, rather than silently overwriting the first
decision's `approved`/`reviewer` — a retried `mrag review resolve` call, a second reviewer, or a
compromised credential cannot flip an existing decision without detection.

## Drift detection

`eval/drift_detection.py` is pure and offline — it takes `list[Feedback]`/`list[DocumentRecord]`/
review-queue counts and returns a `DriftReport`. It never opens a database connection or reads a
manifest itself.

- **Feedback-driven metrics** (`FeedbackDriftMetrics`): thumbs-up/down rate, correction rate, and
  (when callers report `citation_count`) empty-retrieval rate. `is_test=True` feedback is
  excluded.
- **Document freshness** (`DocumentFreshnessMetrics`): the fraction of the corpus not updated
  within a configurable window, derived from `LifecycleLedger.export_all()`'s
  `DocumentRecord.updated_at`.
- **Escalations** (`EscalationMetrics`): pending/resolved review-item counts and an escalation
  rate (`pending / total_feedback`).
- **`compute_drift(current, baseline)`** compares two snapshots and flags any metric that
  degraded past a threshold (`0.02` default, matching `ROADMAP.md`'s own "alert if degrading >
  2%" wording for V3.2). `should_trigger_retraining` is advisory only — per ADR-0005 §5.2, this
  framework decides *when* retraining might be warranted; it never runs a retraining job itself.
- **`select_feedback_for_reevaluation()`** selects feedback carrying a human-provided
  `correction_text` as candidates for offline re-scoring. It does not re-score anything — see
  ADR-0014's "Explicitly out of scope" note on why (the original answer's full text/citations are
  not durably persisted anywhere in this codebase today).

Feedback metrics are aggregated over **disjoint, non-overlapping observation windows** — never
cumulative history, and never two windows that partially overlap each other (Codex review pass 1
HIGH-001, reopened and corrected in pass 2: an earlier version bounded both the baseline and
every comparison snapshot to a trailing `--window-days` window measured back from each run's own
generation time, which still let baseline-era records reappear in the current window whenever
the two runs happened close together — diluting a severe recent regression exactly as the
original, pre-windowing bug did).

- **Establishing a baseline** (`--update-baseline`) captures a trailing `--window-days` window
  (default 7) ending at that moment — persisted as explicit `window_start`/`window_end`
  boundaries, not just a duration.
- **Comparing against a baseline** always starts the current window exactly at the baseline's own
  `window_end` — structurally disjoint from it, so no record can be counted in both. `--window-days`
  on a comparison run instead sets the *minimum elapsed time* required since the baseline's window
  ended before the comparison is considered meaningful; comparing too soon after establishing a
  baseline is rejected (non-zero exit) rather than silently run against a too-short current
  sample.
- **`--window-days` must be `>= 1`** — a zero or negative value is rejected immediately (before
  the manifest is even loaded), rather than silently excluding all current feedback and reporting
  a structurally valid but empty drift snapshot.
- A baseline written before this fix (no persisted `window_end`) is rejected with an actionable
  message on the next comparison — regenerate it with `--update-baseline`.

```bash
# First run — establish a baseline covering the last 7 days:
python scripts/run_drift_check.py --manifest manifests/presets/secure-enterprise-rag.yaml \
    --update-baseline --baseline drift-baseline.json --window-days 7

# Later runs — compare against it. --window-days here is the minimum time
# that must have elapsed since the baseline before the comparison runs
# (rejected if run too soon after --update-baseline above):
python scripts/run_drift_check.py --manifest manifests/presets/secure-enterprise-rag.yaml \
    --baseline drift-baseline.json --window-days 7
```

Like `scripts/run_benchmark.py`, this is never manifest-activated and has no scheduler of its
own — run it manually or wire it into an external cron/scheduled job.

## Explicitly out of scope

See [ADR-0014](../adr/0014-feedback-drift-and-human-review.md)'s own "Explicitly out of scope"
section: automated re-scoring of selected feedback, a reversible pseudonymizer (M1) for
`correction_text`, new public REST endpoints for reviewing/resolving items, per-tenant retention,
a manifest-activated drift gate, and real online empty-retrieval telemetry (the empty-retrieval
signal here is caller-reported, corroborating `mrag.retrieve.empty`'s existing real-time
`Meter`-based counter, ADR-0013 — not a replacement for it).
