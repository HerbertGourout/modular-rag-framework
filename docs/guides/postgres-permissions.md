# PostgreSQL role and permission setup

ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention). This
guide documents the DB-permission-level enforcement that makes `audit_events`
append-only *in fact*, not merely by Python-level convention
(`PostgresAuditSink` never issues an `UPDATE`, and its one `DELETE` —
`purge_expired()` — is gated behind an explicit `allow_purge=True` constructor
flag; see that method's docstring). Permission separation is the compensating
control for the case where that Python-level gate is bypassed or
misconfigured: even a fully-compromised application process, running with the
`app_role` credentials below, structurally cannot alter or delete a single
audit row.

This document is SQL to run once against your PostgreSQL instance, by a
superuser or a role with `CREATEROLE`/`GRANT` privileges — it is not automated
tooling (no Terraform/Ansible provided), the same "documented commands, not
reimplemented as framework code" precedent already used for `pg_dump`/
`pg_restore` in [docs/guides/backup-restore.md](backup-restore.md).

## Two roles

| Role | Used by | Privileges | Never has |
|---|---|---|---|
| `app_role` | The running application (`PostgresLifecycleLedger`/`PostgresAuditSink`/`PostgresFeedbackSink`/`PostgresReviewQueue` as wired through a manifest's `audit_sink:`/`lifecycle_ledger:`/`feedback_sink:`/`review_queue:` block) | `INSERT`, `SELECT` on `audit_events` and `feedback`; `INSERT`, `SELECT`, `UPDATE` on `document_lifecycle` and `review_items` (both are intentionally mutable — see each's own module docstring) | `DELETE` on `audit_events`/`feedback`/`review_items`. No `CREATE`/DDL privilege on any table — schema ownership belongs to `migration_role` (see below) |
| `retention_role` | Only the retention-purge CLI invocations (`mrag audit purge`/`mrag feedback purge`/`mrag review purge --dsn ...`), run by an operator or a scheduled job — a **different DSN** than the application's own | `DELETE` on `audit_events`, `feedback`, and `review_items` (in addition to `SELECT`, for each's `count_expired()`) | Write access to `document_lifecycle` — this role's only job is retention across the three append-or-mutate-but-never-delete tables above |

A third role, `migration_role`, owns the schema itself (`CREATE`/`ALTER`/
`DROP` on both tables) and is the one `mrag db migrate` / `auto_migrate=True`
should connect as — never the same credentials the running application uses.
`auto_migrate=True` is documented as a local/dev convenience precisely because
it needs this broader, DDL-capable role; production deployments should run
`mrag db migrate` once, out-of-band, with `migration_role`, and leave the
application's own `auto_migrate` at its default `False`.

## SQL

```sql
-- Run once, as a superuser or an equivalently privileged role.

CREATE ROLE migration_role LOGIN PASSWORD '...';
CREATE ROLE app_role LOGIN PASSWORD '...';
CREATE ROLE retention_role LOGIN PASSWORD '...';

-- migration_role owns the schema. Run `mrag db migrate` (or construct an
-- adapter with auto_migrate=True) using this role's DSN.
GRANT CREATE ON SCHEMA public TO migration_role;

-- After migrations have run at least once (document_lifecycle, audit_events,
-- feedback, and review_items all exist):

GRANT SELECT, INSERT, UPDATE ON document_lifecycle TO app_role;
GRANT SELECT, INSERT ON audit_events TO app_role;
GRANT SELECT, INSERT ON feedback TO app_role;
GRANT SELECT, INSERT, UPDATE ON review_items TO app_role;
-- Deliberately no DELETE grant on audit_events/feedback/review_items for
-- app_role. review_items gets UPDATE (PostgresReviewQueue.resolve()'s own
-- resolution write) but never DELETE, same as document_lifecycle.

GRANT SELECT, DELETE ON audit_events TO retention_role;
GRANT SELECT, DELETE ON feedback TO retention_role;
GRANT SELECT, DELETE ON review_items TO retention_role;
-- Deliberately no INSERT/UPDATE grant for retention_role — it can remove
-- expired rows, nothing else.

-- If migrations add new tables in the future, re-run the two GRANT
-- statements above for the new table names — table-level grants are not
-- retroactive to tables that did not exist yet when the GRANT ran. (ADR-0014
-- is the most recent example: adapters/postgres/sql/0005_feedback.up.sql and
-- 0006_review_items.up.sql added the two tables the grants above cover.)
```

## Why not just trust the Python-level `allow_purge` gate?

Because a single mistake — a manifest accidentally wired with the
`retention_role` DSN instead of `app_role`'s, or a future code change that
forgets to check `self._allow_purge` — should not be the only thing standing
between a compromised or buggy process and deleting compliance evidence.
Defense in depth: the Python gate stops an accidental/internal call path from
reaching `purge_expired()`; the DB-role separation stops the *credentials*
`app_role` actually holds from ever being able to run a `DELETE` against
`audit_events`, regardless of what Python code executes.

## What this does not cover (recorded honestly, not silently skipped)

- **Not tamper-evident.** A `DELETE`-capable role existing at all — even one
  restricted to the retention job — means this is permission-separation, not
  cryptographic/WORM immutability. A regulatory requirement for true
  immutability needs object-lock/WORM storage (e.g. a write-once S3 bucket
  mirroring `audit_events`, out of scope for this guide) or a
  database-level mechanism PostgreSQL does not provide natively (append-only
  tables via `pg_audit`-style extensions are a partial mitigation, not
  covered here).
- **Retention is currently global, not per-tenant.** `AuditEvent.retention_days`,
  `Feedback.retention_days`, and `ReviewItem.retention_days` all default to
  `365`, and nothing in this codebase today sets any of them to anything
  else — a tenant-specific retention policy would need that field actually
  varied at write time, which is out of scope here.
- **Backups outlive purges.** `pg_dump` snapshots (see
  [backup-restore.md](backup-restore.md)) captured before a `purge_expired()`
  run still contain the purged rows. A backup-rotation policy shorter than
  the shortest configured `retention_days` is required to make retention
  meaningful end-to-end; this guide does not set one.
- **No per-subject erasure path.** `audit_events.actor`, `feedback.submitted_by`,
  and `feedback.correction_text` (post-redaction) can all be or reference
  personal data; neither `RAGEngine.erase_document()` nor anything else in
  this codebase removes a specific person's rows from any of the three
  governance tables on request. If a legal erasure obligation applies to
  these records specifically (as opposed to indexed document content, which
  `erase_document()` does cover), that is a deliberate, documented gap, not
  an oversight.
- **Purge events are logged, not self-audited.** `purge_expired()` on any of
  the three sinks (`PostgresAuditSink`/`PostgresFeedbackSink`/
  `PostgresReviewQueue`) does not write its own `AuditEvent` recording that a
  purge happened — adding that would mean defining a new `AuditEventType`
  and payload-allowlist entry (`contracts/audit.py`), a contract change out
  of scope here. A structured log line is emitted instead; operators wanting
  a permanent record of purge runs should capture that log stream durably.
