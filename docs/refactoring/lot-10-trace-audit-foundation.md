# Lot 10 — Versioned Trace/Audit Foundation

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 7 (`DocumentEngine` port — not directly used here, but the same
delegation-boundary discipline applies), Lot 9 (`observability` manifest section, where a real
sink selection will eventually plug in)

## What was done

### Trace-side fix (observability, not compliance)

- **Removed the duplicate/overlapping "generate" timing step.** `RAGEngine._run_steps()`
  (`src/modular_rag/orchestration/engine.py`) used to wrap the generator call in its own
  `TraceStep(name="generate", ...)` *in addition to* the generator's own self-instrumentation
  (`openai_gen.py`/`anthropic_gen.py` both already call `trace.add_step()` internally with
  real token counts, per `.claude/.instructions.md` §3's documented pattern). Both steps measured
  overlapping — not identical — time windows, so `trace.total_latency_ms` double-counted
  generation latency. Fixed by deleting the engine's own wrapping step; the generator's own step
  is now the only one. Regression test:
  `tests/unit/orchestration/test_engine.py::test_answer_does_not_double_count_generation_latency`.
- **`TRACE_SCHEMA_VERSION = "1.1"`** added to `core/models/trace.py`, with `Trace.schema_version`
  defaulting to it — the first explicit version marker on this model, so future consumers can
  detect the generation-latency semantics changed.
- **`Trace.failed: bool` / `Trace.failure_reason: str | None`** added. Previously, a failed run
  (guard block, retrieval error, generation error) skipped `telemetry.record_trace()` entirely —
  no observability evidence existed for the failure at all. `RAGEngine._run()` was refactored
  into a thin try/except wrapper (sets `failed`/`failure_reason`, still records to telemetry, then
  re-raises unchanged) plus a `_run_steps()` method holding the original step sequence. Regression
  tests: `test_failed_runs_still_reach_telemetry_marked_failed`,
  `test_successful_runs_are_recorded_as_not_failed`.

### Compliance-audit contract (new capability, not a fix)

Per docs/refactoring-plan.md §09/CLAUDE.md V1.2 ("`security/audit/`: Immutable append-only event
store"), deliberately kept separate from `Trace`: a `Trace` is execution/performance
observability; an `AuditEvent` is compliance evidence, with a payload structure that can't
silently carry PII/secrets.

- **`contracts/audit.py`** (new): `AuditEvent` (Pydantic model — `schema_version`,
  `correlation_id`, `causation_id`, `tenant_id`, `actor`, `event_type`, `timestamp`, `payload`,
  `retention_days`), `AuditEventType` (`StrEnum`: query_received, retrieval_performed,
  generation_performed, guard_decision, run_succeeded, run_failed), and the `AuditSink` Protocol
  (`record`/`arecord`/`name` — deliberately no update/delete method: append-only by contract, not
  just by convention).
- **PII/secret allowlist**: `ALLOWED_PAYLOAD_KEYS` is a `frozenset` of the only keys
  `AuditEvent.payload` may contain (`query_text_redacted`, `chunk_ids`, `answer_length`,
  `citation_count`, `guard_decision`, `guard_reason`, `policy_refs`, `model_name`, `latency_ms`,
  `error_type`). A `field_validator` rejects any other key at construction time — an explicit
  allowlist, not a denylist, so a new sensitive field introduced elsewhere in the codebase must be
  deliberately added here before it can reach audit storage. Test:
  `tests/unit/contracts/test_audit.py::test_audit_event_rejects_non_allowlisted_payload_keys`.
- **`security/audit/store.py`**: `InMemoryAuditSink` — a real reference implementation (not a
  mock), append-only (`events` property returns a defensive copy), with an
  `events_for_correlation()` helper for tests/inspection. Exported from `security/__init__.py`
  alongside `BasicSecurityGuard`/`PatternRedactor`.
- **`adapters/audit/postgres_sink.py`**: `PostgresAuditSink` — the durable backend, per the
  infra-stack decision already recorded in this plan's decision log (2026-08-03, "PostgreSQL
  (Lot 10 audit store, Lot 12a lifecycle ledger)"). Lazy-imports `psycopg` (per
  `.claude/.instructions.md` §4 — not declared in the `v1` extra; audit persistence is opt-in
  infrastructure, install with `pip install psycopg[binary]>=3.1`). Owns its own DDL
  (`CREATE TABLE IF NOT EXISTS audit_events ...`), inserts with `ON CONFLICT (id) DO NOTHING` so a
  retried `record()` call can never overwrite an existing row. True append-only enforcement at the
  database-permission level (a role without UPDATE/DELETE grants) is a deployment concern, not
  something this Python adapter can guarantee alone — flagged for Lot 16c's runbooks.
- **`tests/integration/test_postgres_audit_sink.py`** (new, `@pytest.mark.integration`): exercises
  a real PostgreSQL instance on `localhost:5432` (or `MRAG_TEST_POSTGRES_DSN`), same
  "assumes a running local service" convention as `tests/integration/test_qdrant_store.py`. Not
  run as part of this lot's `check.sh full` (which only runs `tests/unit` + `tests/contract`, no
  Qdrant/Postgres in this environment) — real, ready-to-run code, consistent with the existing
  integration-test pattern established before this lot.

### Wiring into `RAGEngine`

- **`Container.audit_sink`** (new optional property, `app/container.py`) — mirrors `telemetry`'s
  optionality (`_store.get(...)`, defaults to `None`) so existing manifests/tests are completely
  unaffected unless a caller explicitly registers one.
- **`RAGEngine._audit()`** (new private method) — records one `AuditEvent` per run: `RUN_SUCCEEDED`
  (payload: `answer_length`, `citation_count`) on success, `RUN_FAILED` (payload: `error_type`) on
  any exception, using `trace.id` as `correlation_id`. No-op when `audit_sink` isn't configured.
  `tenant_id` is read from `query.metadata.get("tenant_id", "unknown")` — `Query`
  (`core/models/query.py`) has no dedicated tenant field yet, and adding one is explicitly Lot 11b
  scope ("Propagate authenticated identity and tenant through `ExecutionContext`"). Using the
  existing free-form `metadata` dict avoids anticipating that design. Tests:
  `test_answer_records_a_run_succeeded_audit_event`,
  `test_answer_records_a_run_failed_audit_event_when_guard_blocks_query`,
  `test_answer_uses_tenant_id_from_query_metadata_when_present`,
  `test_answer_records_no_audit_event_when_no_audit_sink_is_configured`.

### Convention correction made while implementing this lot

Initially added `__init__.py` files to `adapters/audit/` and `security/audit/` to re-export their
public classes. Checked against the actual repository convention first
(`adapters/vectorstores/`, `adapters/embeddings/`, `security/filters/`, `security/redaction/`,
`security/policies/`, `security/detectors/` — **none** of these subdirectories have an
`__init__.py`; they're plain namespace packages, imported by their full submodule path). Removed
both files to match; `InMemoryAuditSink` is instead re-exported from the existing
`security/__init__.py` (which already aggregates `BasicSecurityGuard`/`PatternRedactor` the same
way), and `PostgresAuditSink` has no package-level re-export, consistent with
`adapters/vectorstores/` having none for `QdrantStore` either.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 315 tests total (252 unit + 63 contract, up from 296 at Lot 9): +5 `contracts/audit.py` unit
  tests, +3 `security/audit/store.py` unit tests, +4 `test_answer_records_*`/`test_answer_uses_*`
  engine-wiring tests, +4 `test_audit_conformance.py` contract tests.
- mypy baseline unchanged at 35 — zero new errors.
- `tests/integration/test_postgres_audit_sink.py` written and reviewed but not executed in this
  environment (no local PostgreSQL) — same status as the pre-existing Qdrant integration tests.

## Lot 10 acceptance (per `docs/refactoring-plan.md` §6)

"Stable trace/audit schemas; complete success/failure evidence; no raw secret/PII leakage" — all
three delivered:
- **Stable schemas**: `TRACE_SCHEMA_VERSION = "1.1"` and `AUDIT_SCHEMA_VERSION = "1.0"`, both
  carried as a field on every instance.
- **Complete success/failure evidence**: `Trace.failed`/`failure_reason` plus a `RUN_SUCCEEDED`/
  `RUN_FAILED` `AuditEvent` on every run, success or failure — closes the exact gap named in
  `docs/refactoring-plan.md` §2 ("Trace semantics... failed executions may not persist complete
  evidence" and "Audit semantics... compliance evidence cannot be guaranteed").
- **No raw secret/PII leakage**: `ALLOWED_PAYLOAD_KEYS` enforced by a Pydantic validator, not a
  convention — an unlisted key fails construction, not just code review.

**Not fully closed by this lot** (per §10's open question, "Audit retention, immutability,
residency, and legal requirements... Sink and schema policy remain provisional"):
`AuditEvent.retention_days` is *metadata* (a field recorded on each event, default 365), not
*enforcement* — no scheduled deletion job exists yet, and residency/legal requirements (where the
Postgres instance may legally live, cross-border transfer rules) remain undecided. True
append-only immutability is a database-permission concern flagged for Lot 16c, not proven here.
These are recorded as still-open, not silently dropped.

## Next

Lot 11a (threat model and data-classification policy) is next per the plan's phase-C ordering —
it's a paper-and-fixture deliverable that Lot 11b's identity/tenant enforcement then depends on.
Lot 11b is also where `Query`/`ExecutionContext` gets a real tenant field, at which point
`RAGEngine._audit()`'s `query.metadata.get("tenant_id", "unknown")` placeholder should be replaced
with the enforced value.
