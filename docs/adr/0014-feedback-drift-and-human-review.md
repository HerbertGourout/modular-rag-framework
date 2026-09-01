# ADR-0014 — Feedback Contract, Durable Human Review, and Offline Drift Detection

**Status:** Accepted
**Date:** 2026-08-28
**Authors:** Claude Code (implementation)

---

## Context

Batch 14 (external plan — "Feedback, drift, and human review") asks for: a feedback contract, an
authenticated feedback endpoint, durable feedback/review storage, offline drift metrics
(feedback-driven quality drift, document freshness, empty retrieval, review escalations), a
sensitive-content policy for feedback text, retention/deletion, and idempotent submission.

Two existing ADRs constrain this directly:

- **ADR-0008** (offline evaluation and honest engine activation): gold-dependent
  evaluation/quality-gate logic must stay a native, offline, programmatic capability, never an
  online/manifest-activated blocking gate. Drift computation in this ADR follows the same rule —
  it is script-driven (mirroring `scripts/run_benchmark.py`), never a runtime pipeline component,
  and never blocks an answer synchronously.
- **ADR-0005 §5.2** (reframed by `CLAUDE.md` V3.2): fine-tuning *execution* is delegated to
  external MLOps tooling; deciding *when* retraining is warranted (drift detection, the
  evaluation trigger) stays native. This ADR implements exactly that boundary: `eval/
  drift_detection.py` produces a report and a `should_trigger_retraining` flag; nothing in this
  codebase runs a retraining job.

`contracts/review.py`'s `ReviewItem`/`ReviewQueue` and `security/policies/human_review.py`'s
`HumanReviewGate` already exist (Lot 11c) but are in-memory only — that class's own docstring
already anticipated a durable backend "once actually needed." `contracts/audit.py`'s `AuditEvent`/
`AuditSink` establish the durable-governance-record pattern this ADR reuses (Postgres migration
numbering, `retention_days` + `purge_expired()` gated by `allow_purge`, DB-role separation per
`docs/guides/postgres-permissions.md`) rather than inventing a new one.

No feedback contract exists today. `trace_id` (`Answer.trace_id` → `Trace.id`) is the only
identifier this codebase currently returns to an API caller — `request_id`/`correlation_id` are
generated per-call inside `ApplicationService` and never leave the process — so it is the only
usable link between a client's feedback submission and the answer it concerns.

Every prior new contract in this repository (`VectorIndexer` ADR-0009, `HealthCheckable`
ADR-0010, the Postgres retention model ADR-0011, `Tracer` ADR-0012, `Meter` ADR-0013) has its own
ADR per `CLAUDE.md` §07 ("any new top-level module... or contract modification requires a new
ADR"). This ADR is that record for `contracts/feedback.py` and the additive `ReviewItem.
retention_days` field.

## Decision

1. **New, additive contract**: `contracts/feedback.py` defines `Feedback` (a `BaseModel`) and
   `FeedbackSink` (a `Protocol`, mirroring `AuditSink`'s `record()`/`arecord()`/`name()` shape
   exactly). This is a new file, not a change to any existing Protocol — no existing
   implementation needs migration.

   `Feedback.trace_id: str` is required and is the sole link back to the answer it concerns, per
   the identifier-availability finding above. `Feedback.idempotency_key: str` is required and is
   the sink's dedup key, scoped per tenant — a unique index on
   `(COALESCE(tenant_id, ''), idempotency_key)` in Postgres, a `(tenant_id, idempotency_key)`
   tuple key for the in-memory sink — a retried submission for the same tenant is a silent
   no-op, not an error, matching how `PostgresAuditSink.record()`'s `ON CONFLICT (id) DO NOTHING`
   already treats a retried audit write. The uniqueness is scoped by tenant rather than a bare
   constraint on `idempotency_key` alone because the key is a client-supplied, untrusted value:
   a global-uniqueness design would let one authenticated tenant pre-claim another tenant's key
   and silently swallow their feedback via the same `ON CONFLICT DO NOTHING` path.

2. **`ReviewItem` gains `retention_days: int = Field(default=365, ge=1)`** — purely additive with
   a default, the same shape and default `AuditEvent.retention_days` already established
   (ADR-0011). This is a `BaseModel` field addition, not a `ReviewQueue` Protocol method change —
   `contracts/CLAUDE.md`'s ADR-before-Protocol-change rule concerns method signatures on the
   Protocol itself; every existing `ReviewItem(...)` construction remains valid unchanged.

3. **Durable backends mirror the audit-sink pattern exactly**: `adapters/feedback/postgres_sink.py`
   (`PostgresFeedbackSink`) and `adapters/review/postgres_queue.py` (`PostgresReviewQueue`) reuse
   `core/resilience.py`'s `CircuitBreaker`/`retry_with_backoff`, the same connection-pool/health-
   check/purge-batching shape as `PostgresAuditSink`, and the same migration numbering scheme
   (`adapters/postgres/sql/0005_feedback.{up,down}.sql`, `0006_review_items.{up,down}.sql`).
   `docs/guides/postgres-permissions.md` gets the two new tables' `GRANT` lines, per that guide's
   own "if migrations add new tables in the future" instruction. `PostgresReviewQueue.
   should_review()` stays a pure, in-memory confidence-threshold check (no DB round-trip on the
   `RAGEngine.answer()` hot path) — only `enqueue()`/`resolve()` write through.

4. **New optional container role, `feedback_sink`** — registered in `orchestration/registry.py`,
   exposed as `Container.feedback_sink` (mirrors `audit_sink`/`review_queue`'s existing `X | None`
   optionality exactly), factories registered in `app/default_factories.py` for `"in-memory"` and
   `"postgres"` types. A new `"postgres-human-review"` factory is added for the existing
   `review_queue` role, alongside the existing in-memory `"human-review"` one — `ReviewQueue`
   itself is unchanged.

5. **Sensitive-content policy: redaction is the explicit gate, not a default-on convenience.**
   `RAGEngine.record_feedback()` refuses `Feedback.correction_text` outright (raises
   `ConfigurationError`) unless a `redactor` is wired on the same container — wiring
   `governance.redactor` *is* the "explicit policy" the task asks for. When wired, `correction_
   text` is passed through `Container.redactor.redact()` (the existing, destructive
   `PatternRedactor` — DIGEST-security.md's M0 mitigation) before a `Feedback` object is ever
   constructed for storage. No reversible pseudonymizer (M1) is added — that remains the
   documented V1.2 backlog item in `docs/research/DIGEST-security.md`, a larger, separate
   decision this batch does not need.

6. **`Feedback.is_test: bool = False`, enforced at the API/application layer, not the contract.**
   A caller may only set `is_test=True` when the verified identity's `roles` contains `"tester"`
   (`contracts/identity.py::TenantContext.roles`, an existing, previously-unconsumed field) —
   otherwise `ApplicationService.record_feedback()` raises `SecurityError` (already mapped to
   HTTP 403 by `api/errors.py::to_http_exception`, no new error-mapping code needed).
   Drift computation (`eval/drift_detection.py`) excludes `is_test=True` records by default, so
   QA/synthetic feedback traffic cannot silently skew a real drift signal.

7. **Drift detection is a pure, offline computation module — `eval/drift_detection.py`** — the
   exact module path `ROADMAP.md`'s V3.2 already names. It takes plain data (`list[Feedback]`,
   `list[DocumentRecord]`, review-queue counts) and returns a `DriftReport`; it never opens a
   database connection or reads a manifest itself, so it stays trivially unit-testable and
   `eval/`-layering-compliant (`contracts/` + `core/models/` only). A companion script,
   `scripts/run_drift_check.py` (outside `src/modular_rag/`, mirroring exactly why `scripts/
   run_benchmark.py` lives there — it needs `app`/`orchestration` imports `eval/` itself cannot
   make), does the actual "wire a manifest, read the durable stores, call the pure function,
   print/write a report" orchestration. Per ADR-0008, no manifest ever activates this — it is
   script-driven only, same as the offline benchmark.

   `select_feedback_for_reevaluation()` (also in `eval/drift_detection.py`) is a narrow selection
   function: it filters stored feedback down to records carrying a non-null `correction_text`
   (a human-provided correction is, in effect, an ad-hoc gold answer for that one query). It does
   **not** re-run scoring itself — see "Explicitly out of scope" below.

8. **Human-review resolution stays a CLI operation, not a new public REST surface** — `mrag review
   resolve`/`list-pending`/`purge`/`count-expired`, mirroring `mrag audit purge`/`count-expired`'s
   existing DSN-based trust model exactly (an operator-supplied `--dsn`, no `TokenVerifier`
   concept, same as every other CLI command per `docs/architecture/security.md`). "Durable and
   secure" is satisfied by the DB-role separation (§3 above) plus this CLI's existing trust model,
   not by inventing new API-level RBAC for an administrative operation this codebase's own
   convention already keeps out of the REST surface.

9. **Observability signal, decided explicitly per `.claude/.instructions.md` §3**: recording
   feedback is a synchronous, online execution stage, so it gets the same treatment `answer()`/
   `retrieve()` already get — an `app.request` span (`ApplicationService._request_span("feedback",
   ...)`, with `app.trace_id` set from the caller-supplied `trace_id`) plus the existing RED
   metrics (`_record_request_metrics("feedback", ...)`), and `POST /feedback` is added to
   `TracingMiddleware._TRACED_PATHS` so an auth/validation failure before the route body runs is
   not invisible to tracing (the same MEDIUM-001 gap `/answer`/`/retrieve` already closed).
   Drift computation (`eval/drift_detection.py`) gets **none** of the three signals — it is a pure,
   offline function with no manifest activation, so there is no online request boundary to
   instrument (matching the offline benchmark's own precedent, ADR-0008). Human-review resolution
   (`mrag review resolve`) also gets none — it is a CLI operation, and the durable `review_items`
   row itself is the record of what happened, per `mrag audit`'s existing CLI trust model
   (decision 8).

## Explicitly out of scope

- **Automated re-scoring of selected feedback.** `select_feedback_for_reevaluation()` only
  selects candidates. Actually re-running them through `eval/scorers/answer_correctness.py`
  requires the original answer's full text/citations to be durably retrievable, which nothing in
  this codebase persists today (a `Trace`/`Answer` is not stored beyond `Telemetry`'s post-hoc,
  usually in-memory recording) — durably persisting full answer content is a separate, larger
  storage decision this batch does not make.
- **A reversible pseudonymizer (M1) for feedback text.** Destructive redaction (M0, decision 5) is
  the policy; a mapping-based reversible scheme is `docs/research/DIGEST-security.md`'s own noted
  V1.2 backlog item, not required by this batch's acceptance criteria.
- **New public REST endpoints for listing/resolving review items.** See decision 8.
- **Per-tenant retention variation.** `Feedback.retention_days`/`ReviewItem.retention_days` both
  default to `365` and nothing sets them otherwise — the same accepted, already-documented
  limitation `docs/guides/postgres-permissions.md` records for `AuditEvent.retention_days`.
- **A manifest-activated drift gate.** Per ADR-0008, this stays script/CLI-driven; a runtime
  quality gate with no gold dependency remains a distinct, larger future decision that ADR itself
  already names as its own precondition.
- **Real online "empty retrieval" telemetry.** `eval/drift_detection.py`'s empty-retrieval signal
  is derived from `Feedback.citation_count` (an optional field the feedback caller — which already
  has the answer's citation list when rendering the feedback widget — may report), not from new
  backend instrumentation. A `Meter`-based online empty-retrieval counter already exists
  (`mrag.retrieve.empty`, ADR-0013) for real-time alerting; this offline signal is a
  feedback-corroborated view for the drift report specifically, not a replacement for it.

## Consequences

**Positive:**
- Feedback, drift, and human-review durability all reuse this codebase's one existing durable-
  governance pattern (Postgres + migrations + retention/purge + DB-role separation) instead of
  introducing a second one — the same review/operational discipline
  (`.claude/rules/health-checks.md`) that closed `PostgresAuditSink`'s five-round history is
  inherited from the start, not re-derived.
- Drift detection is pure and offline, so it cannot regress ADR-0008's boundary or the online
  answer path's latency, regardless of how it evolves.

**Negative / accepted risk:**
- No automated re-scoring pipeline exists yet for corrections a human review flags as
  gold-quality — an operator must act on `select_feedback_for_reevaluation()`'s output manually
  today.
- `empty_retrieval_rate` depends on callers honestly reporting `citation_count`; a caller that
  never sets it makes that one signal silently absent from the drift report, not wrong — the
  report distinguishes "0 citations reported" from "citation_count never reported" the same way
  Batch 13's `cost_measured_count` distinguishes "confirmed zero" from "never measured".

## References

- [ADR-0008](0008-offline-evaluation-and-engine-activation.md) — the offline/non-blocking
  constraint this ADR's drift detection follows.
- [ADR-0005 §5.2](0005-document-ai-control-plane-boundary.md) — native drift-detection/
  evaluation-trigger vs. delegated fine-tuning execution.
- [ADR-0011](0011-postgresql-migrations-pooling-and-retention.md) — the durable-storage,
  retention, and DB-role-separation pattern this ADR reuses rather than reinventing.
- [docs/guides/postgres-permissions.md](../guides/postgres-permissions.md) — updated with the two
  new tables' grants.
- [ROADMAP.md](../../ROADMAP.md) V3.2 — the module paths (`eval/feedback_collection/` reused as
  the `contracts/feedback.py` + sink location; `eval/drift_detection.py` exactly) this ADR
  implements against.
