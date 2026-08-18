# ADR-0011 — PostgreSQL migrations, connection pooling, and audit retention

**Status:** Accepted
**Date:** 2026-08-18

## Context

This work is tracked externally as "Lot 7 — PostgreSQL, migrations et lifecycle" under a
"P2 — Déploiement et CI" phase. That numbering is **not** the same track as this repository's
own `docs/refactoring-plan.md`, which already has a completed, unrelated "Lot 6" (the LangGraph
engine-selection spike, ADR-0006) and "Lot 7" (the `DocumentEngine` contract, ADR-0006/0007's
prerequisite) — both accepted 2026-08-04, both about generic engine delegation, neither about
PostgreSQL at all. To avoid exactly the kind of confusion a grep for "Lot 7" would otherwise
cause, no code or doc touched by this change cites "Lot 7" as its origin — this ADR is the
citation instead.

Two PostgreSQL adapters exist: `adapters/lifecycle/postgres_ledger.py` (`PostgresLifecycleLedger`,
table `document_lifecycle`, mutable) and `adapters/audit/postgres_sink.py` (`PostgresAuditSink`,
table `audit_events`, append-only). Before this change, both:

- Ran an inline `CREATE TABLE IF NOT EXISTS` + index DDL string unconditionally on every fresh
  connection — implicit runtime schema creation, no versioning, no migration history.
- Held exactly one cached `psycopg.Connection` behind a `threading.Lock()` held for each public
  method's entire body — no pooling, one physical connection per adapter instance for the
  process's whole lifetime.
- Had no enforcement of `AuditEvent.retention_days` (`contracts/audit.py`) at all — the field was
  stored per-row and never read back by anything. This was a previously-identified, explicitly
  deferred gap: `docs/refactoring-plan.md` line 560 records "Retention job/DB permissions:
  unscheduled, flag for Lot 17 triage" (never actually picked up there), and
  `docs/refactoring/lot-16c-deployment-runbooks.md`'s "Deliberately out of scope, recorded
  honestly" section names "Audit-retention enforcement (a scheduled deletion job, DB-permission-
  level immutability)" as not built by that lot either.

`check_health()` on both adapters (ADR-0010) was already correct and is **not** touched by the
pooling change — it has always used its own dedicated, throwaway connection, never the shared
one this ADR replaces.

Three specialist review passes ran *before* any code was written (architecture-reviewer,
security-specialist, test-specialist — analysis/review only, Claude remained the sole writer)
and materially changed this design from its first draft; their findings are cited by role below
where they changed a decision.

## Decision

### 1. Migrations

A new subpackage, `adapters/postgres/` (a namespace package, no `__init__.py`, per
`.claude/rules/adapters.md` §8's existing convention — architecture-reviewer confirmed this is
not a top-level module requiring its own ADR trigger under `CLAUDE.md` §07, and is not the
"adapters never import each other" violation that rule exists to prevent: that rule targets
coupling two *backend choices* for one capability, e.g. Qdrant importing from Postgres; this is a
shared *infrastructure* helper with no domain logic and no Protocol, imported by both Postgres
adapters, which already share one physical database in every shipped deployment shape).

- `adapters/postgres/sql/NNNN_name.up.sql` / `NNNN_name.down.sql` — plain SQL files, paired,
  zero-padded sequential version numbers. Shipped **inside** the Python package
  (`src/modular_rag/adapters/postgres/sql/`), not a repo-root `migrations/` directory — the
  latter would not be included in `pip install`'s wheel (`pyproject.toml`'s
  `[tool.hatch.build.targets.wheel]` only packages `src/modular_rag`). Resolved at runtime via
  `importlib.resources`, so this works identically from a dev checkout and an installed wheel.
- `adapters/postgres/migrations.py`'s `MigrationRunner(dsn, migrations_dir=None)`:
  `.migrate(target=None)` applies every pending migration in order; `.rollback(steps=1)` reverses
  the most recently applied migrations via each one's paired `.down.sql`; `.applied_versions()`
  reads the tracking table without mutating anything. Tracked in a `schema_migrations(version,
  name, applied_at)` table the runner creates and owns directly (bootstrap bookkeeping, not
  itself a numbered migration — the same self-managed-tracking-table precedent as Flyway/Django/
  Rails migration tooling).
- **One shared migration set and one `schema_migrations` table**, not a per-adapter/per-namespace
  scheme — architecture-reviewer confirmed this is the right level of generality for exactly two
  tables today, with a `pg_advisory_xact_lock` (see below) as the only extra mechanism needed to
  make it safe for concurrent callers.
- **Migrations run on a dedicated, non-autocommit connection**, never the connection pool §2
  introduces. This was a direct correction from test-specialist's pre-implementation review: a
  `pg_advisory_xact_lock` acquired on an *autocommit* connection (the convention every other query
  in these two adapters uses) releases the instant the lock-acquiring statement's own implicit
  transaction ends — i.e., immediately, making the lock a complete no-op. `MigrationRunner`
  connects with `autocommit=False` and runs the lock-acquire, the pending-migration check, every
  DDL statement, and the `schema_migrations` bookkeeping insert/delete inside **one** explicit
  transaction, committed once at the end — the lock is genuinely held for the whole operation,
  so two processes racing a concurrent `auto_migrate=True` startup (§2) can never apply the same
  migration twice.
- Migration `0001`/`0002` are the two tables' existing schema, extracted verbatim from the retired
  inline DDL strings — no schema change. `0003` adds a plain index on `audit_events."timestamp"`;
  `0004` adds a plain (**not** generated — see §9's second-pass HIGH-001 for why a
  `GENERATED ALWAYS ... STORED` column was tried first and rejected by PostgreSQL) `expires_at`
  column, backfilled once via `UPDATE`, and its own index. Both are genuine "upgrade of an
  existing schema" steps, not merely a re-packaging of what already existed.
- **Down-files are paired to up-files by `(version, name)`, not version alone** — a post-
  implementation Codex review correction (§9, HIGH-001). `discover_migrations()`'s first version
  indexed `.down.sql` files by version number only; a stray or misnamed down-file sharing a
  version with an unrelated up-file would pair with it silently, associating a rollback script with
  a migration it was never written for.

### 2. Retiring implicit runtime schema creation

Both adapters' connection-establishment path no longer runs any DDL. A new `auto_migrate: bool =
False` constructor parameter, when `True`, calls the *same* `MigrationRunner.migrate()` lazily on
first connection — so there remains exactly one source of schema truth (the migration files),
whether applied explicitly via the CLI or implicitly for convenience, never a second, parallel
DDL mechanism. Default `False`: a fresh deployment must run `mrag db migrate` (§5) before first
use; a query against a not-yet-migrated database now fails with a `StorageError` that names the
migrate command explicitly (detecting `UndefinedTable` by exception class name, the same
name-based classification style `_is_connection_level_error()` already uses, so this still never
requires `psycopg` to be importable when a test double is in play). `auto_migrate=True` is
documented (`docs/guides/postgres-permissions.md`) as local/dev convenience only — it needs a
DDL-capable (`CREATE`) database role, which a production deployment's application role should
never hold (§4).

### 3. Connection pooling and reconnection

`self._conn: psycopg.Connection | None` + a per-query `threading.Lock()` are replaced by
`psycopg_pool.ConnectionPool` (`pip install "psycopg[pool]"`, verified against psycopg's own
docs before adding — not guessed). Constructed lazily, `open=False` + a non-blocking `.open(wait=
False)` on first real use (matching every other adapter's `_client`/`_get_client()` no-I/O-in-
`__init__` convention, and avoiding `psycopg_pool`'s own documented deprecation of blocking-open-
in-constructor behavior). `min_size`/`max_size` are manifest-configurable (`**cfg.config`, no
`app/default_factories.py` change needed) but validated in `__init__` (`1 <= min_size <= max_size
<= 32`, raising `ConfigurationError`) — architecture-reviewer flagged that an unguarded, manifest-
driven pool size had no upper bound against `max_connections` exhaustion across two adapters,
multiple replicas, and `/ready`'s own separate bare probe connection.

Reconnection is now mostly the pool's own job: `psycopg_pool.ConnectionPool` disposes of and
replaces a broken or expired connection automatically, with exponential backoff up to a
configurable `reconnect_timeout` — satisfying this lot's "stratégie de reconnexion" acceptance
criterion largely for free, with sensible library defaults, rather than via more hand-rolled
retry logic. What is *not* redundant and is explicitly kept (test-specialist, pre-implementation):
`_is_connection_level_error()`'s exception-class-name MRO walk and the existing `CircuitBreaker`+
`retry_with_backoff` wrapping around `_execute()`. The pool's own reconnection covers connection
*establishment* failures; a connection that dies **mid-query**, after this code has already
checked it out via `with pool.connection() as conn:`, is a failure `_execute()`'s own caller still
needs classified so the *query* gets retried (checking out a fresh connection), which is a
different concern than the pool's internal bookkeeping. The former manual `self._conn = None`
invalidation is gone — there is no more single cached connection to invalidate; the pool decides
on its own whether a returned connection is fit for reuse.

`psycopg_pool.PoolClosed` was added to `_NON_TRANSIENT_SUBCLASSES` (test-specialist finding,
verified live via WebSearch against psycopg's own published source): it subclasses
`psycopg.OperationalError` and lives in a module whose name starts with `"psycopg"`, so without
this exclusion a query issued after `close()` would be retried three times against a
*permanently* closed pool before surfacing the real error, instead of failing immediately.

`pool.connection()`'s checkout is bounded by an explicit, short `timeout=5.0` (`_POOL_CHECKOUT_
TIMEOUT`), distinct from `psycopg_pool`'s own 30-second default — test-specialist flagged that
the default would otherwise compound badly with `retry_with_backoff`'s own attempt budget,
producing a far worse tail latency than the single lock this replaces ever had.

`check_health()` is unchanged in its connection strategy — still its own dedicated, throwaway,
non-pooled connection per ADR-0010 — with one addition (§4 below).

### 4. `check_health()` gains a schema-existence check

architecture-reviewer (pre-implementation) identified a readiness regression §2 would otherwise
introduce silently: today, a reachable-but-schema-less database self-heals on the first real
connection via the inline DDL; after retiring that, `check_health()`'s `SELECT 1` would keep
reporting `healthy` while every real query failed with "relation does not exist." `SELECT 1` is
replaced by `SELECT to_regclass('<table>') IS NOT NULL` — the same single query, same cost, now
also proving the expected table exists. A `False` result reports a hand-authored, non-sensitive
detail string ("schema not migrated ... run `mrag db migrate`"), exempt from the raw-exception-
leak classification requirement for the same reason Qdrant's collection-validation messages are
(ADR-0010 §5: fully self-authored, drawn only from internally-known values, not external
exception content).

### 5. Retention enforcement

`PostgresAuditSink.purge_expired(now: datetime | None = None) -> int` — the sink's one and only
`DELETE` statement, batched (500 rows per statement, looped until an *empty* batch — see §9's
MEDIUM-002 for why empty, not merely short), executed without automatic retry (§9's second-pass
MEDIUM-001) so a large backlog does not hold one long-lived table lock on an autocommit
connection. Filters on a plain `expires_at` column populated by `record()` at write time (§9's
MEDIUM-003 and its own second-pass HIGH-001 correction; originally an inline
`"timestamp" + make_interval(days => retention_days)` expression evaluated on every query), with
`retention_days > 0` as a defensive guard (`AuditEvent.retention_days` now also carries
`Field(ge=1)` validation at construction — `contracts/audit.py`) and rejects a timezone-naive
`now` explicitly (the column is `TIMESTAMPTZ`; a naive value would otherwise be silently coerced
via the session's own `TimeZone` setting rather than raising). A companion
`count_expired(now=None) -> int` is a SELECT-only dry-run/monitoring variant, deliberately **not**
gated behind the same guard as the destructive method (see next paragraph) — security-specialist's
explicit recommendation against a single `dry_run=` flag on one method, which is a classic
flag-inversion footgun; two distinctly-named methods make the safe one obviously safe by
inspection.

`purge_expired()` raises `SecurityError` unless the instance was constructed with a new, fail-
closed `allow_purge: bool = False` flag explicitly set `True`. This was security-specialist's
primary structural finding: DB-role separation alone (§6) is the right *compensating* control,
but a single misconfiguration (an app-role DSN that accidentally has `DELETE`) should not be
sufficient on its own to let a purge run through the ordinary request-serving instance. The
manifest-wired instance used by the live application never sets `allow_purge=True` **— now
structurally, not just by convention** (§9's remaining-risks fix: `app/default_factories.py`'s
`audit_sink: postgres` factory strips `allow_purge` from a manifest's `config:` block before
construction, since generic `**cfg.config` forwarding meant a manifest *could* have set it despite
this paragraph's original claim that it never would). Only a dedicated instance the CLI (§7)
constructs from an explicit `--dsn` argument can set it — two independent things have to be
misconfigured at once, not one. (`SecurityError`'s docstring in `core/errors.py` was broadened,
not narrowed, to cover this: "a security-sensitive administrative operation ... refused by a
fail-closed authorization check," alongside its original "a security guard blocks a query or
answer" scope.)

A purge run is **not** self-audited (no new `AuditEvent` recording that a purge happened) —
doing so would require a new `AuditEventType` and payload-allowlist entry, a `contracts/audit.py`
change judged out of this lot's narrow scope (security-specialist's own recommendation:
"log, don't self-audit, this lot"). A structured `structlog` log line (`audit_purge_completed`,
with the row count and cutoff) is emitted instead, recorded as an explicit residual limitation in
`docs/guides/postgres-permissions.md`, not silently omitted.

### 6. DB-permission-level append-only enforcement

`docs/guides/postgres-permissions.md` — SQL only, not automated provisioning tooling (matching
`docs/guides/backup-restore.md`'s existing "documented commands, not reimplemented as framework
code" precedent for `pg_dump`/`pg_restore`). Three roles: `migration_role` (owns the schema — the
only role that should ever run `mrag db migrate` / construct an adapter with `auto_migrate=True`),
`app_role` (the running application's own DSN — `INSERT`/`SELECT` on `audit_events`, no
`UPDATE`/`DELETE` at all; `INSERT`/`SELECT`/`UPDATE` on the mutable `document_lifecycle`), and
`retention_role` (a **separate** DSN used only by the purge CLI invocation — `SELECT`/`DELETE` on
`audit_events`, nothing else). This directly resolved a blocker security-specialist raised
against an earlier draft of this design: retiring the inline DDL (§2) was a *precondition* for
this permission scheme to even function, since an INSERT/SELECT-only `app_role` attempting the
old unconditional `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS` on every connect
would have failed at cold start on insufficient schema-`CREATE` privilege.

The permissions guide records several residual limitations explicitly rather than silently: not
tamper-evident (a DELETE-capable role existing anywhere is permission-separation, not
cryptographic/WORM immutability); retention is currently global (`retention_days` is `365`
everywhere in this codebase, no per-tenant variation exists); backups outlive purges (a `pg_dump`
snapshot predating a purge run still contains the purged rows — no backup-rotation policy is set
by this ADR); no per-subject erasure path exists for `audit_events.actor` specifically.

### 7. CLI

Two additions to `cli/__init__.py` (currently a flat Typer app — no sub-apps existed before this
change):

- `mrag reconcile --manifest <path> --mode check|repair`, following the exact existing pattern
  (`load_pipeline`, `_exit_code_for()`, `_close_application()` in a `finally`) — wraps
  `orchestration.reconciliation.IndexReconciler(container).check()`/`.repair(report)`.
- A new `audit` Typer sub-app: `mrag audit purge --dsn <dsn>` and `mrag audit count-expired --dsn
  <dsn>`. **Deliberately `--dsn`, never `--manifest`** — a direct fix for security-specialist's
  second blocker finding against the initial draft, which would have let the purge command build
  its `PostgresAuditSink` from a manifest's `audit_sink:` block, silently reusing the live
  application's own `app_role` DSN (no `DELETE` grant, so it would simply fail — but worse,
  training operators to expect `--manifest` everywhere invites eventually pasting a privileged DSN
  into a manifest file just to make purge work, defeating §6's separation). `mrag audit purge`
  constructs its own `PostgresAuditSink(dsn=..., allow_purge=True)` directly from the CLI argument
  and never reads a manifest at all.
- A new `mrag db migrate`/`mrag db rollback`/`mrag db status` sub-app, wrapping `MigrationRunner`
  directly against an explicit `--dsn` (same reasoning: schema migration needs `migration_role`'s
  DSN, never the manifest's app-role one).

### 8. Fixed in the same change (pre-existing bug found during inspection, not scope creep)

`tests/integration/test_postgres_lifecycle_ledger.py`, `tests/integration/test_postgres_audit_sink.py`,
and `tests/e2e/test_secure_preset_e2e.py` called a method, `._get_connection()`, that does not
exist on either adapter (the real internal methods have been `_connect_once()`/`_execute()`,
now `_get_pool()`/`_execute()`) — a pre-existing bug, never caught because all three files require
a live PostgreSQL this sandboxed environment and this repository's CI do not provide. Fixed as
part of this same change since it is the exact connection-internals surface this ADR rewrites,
not an unrelated file.

### 9. Post-implementation Codex review

A premium-depth Codex review of the diff (after §1–§8 above had already been implemented and
tested) found two HIGH and three MEDIUM defects the pre-implementation specialist passes did not
catch, since those reviewed the *design*, not the code as actually written. All five were
verified against the real source before fixing, then fixed in the same change:

- **HIGH-001 — a down-file could pair with an unrelated up-file.** Covered above (§1's
  `(version, name)` pairing fix). Also tightened `_VERSION_NAME_PATTERN` from `\d+` to `\d{4}`,
  since the ADR's own `NNNN` naming convention was documented but never actually enforced.
- **HIGH-002 — `record_ingested()`/`tombstone()` were a read-then-write race, not an atomic
  transition.** Not a defect §1–§8 introduced from nothing — `PostgresLifecycleLedger` always
  computed `version = existing.version + 1` in Python from a separate `get()` call before writing
  it back — but the connection pool (§3) made the race *routine*: two concurrent calls for the
  same `document_key` now genuinely execute in parallel on separate physical connections, where
  the single-connection-plus-lock design before this ADR at least serialized (without truly
  preventing) the interleaving. Fixed by making both operations atomic *inside PostgreSQL*
  instead of split across a Python read and a Python write: `record_ingested()` now issues one
  `INSERT ... ON CONFLICT (document_key) DO UPDATE SET version = document_lifecycle.version + 1
  ... RETURNING *` (a fresh row starts at `1` via `VALUES`; an existing row's version increments
  atomically under Postgres's own per-row lock — `created_at` is deliberately absent from `SET` so
  it is preserved untouched on conflict); `tombstone()` is now a single `UPDATE ... RETURNING *`,
  returning `None` when it matches zero rows rather than checking existence with a prior `get()`.
  `restore_record()` keeps the original verbatim-write `_UPSERT`/`_write()` unchanged — it
  legitimately needs to write a caller-supplied version exactly, the backup/restore use case, not
  auto-increment. Proven with a genuine concurrency test in
  `tests/integration/test_postgres_lifecycle_ledger.py`: N separate `PostgresLifecycleLedger`
  instances (separate pools, not just separate threads sharing one) calling `record_ingested()` on
  the same key concurrently must produce every version `1..N` exactly once, no gaps, no repeats —
  written but, like every integration test in this ADR, not executed in this sandboxed environment.
- **MEDIUM-001 — `migrate(target=...)` accepted any string, including one matching no real
  migration.** A target lexically past every known version silently applied everything and
  returned success; a target lexically before the first version silently applied nothing and also
  returned success. Fixed: `target` is now validated against the discovered catalog *before*
  opening a connection, raising `ConfigurationError` immediately on a mismatch.
- **MEDIUM-002 — concurrent purge jobs could over-report how many rows they deleted.**
  `purge_expired()`'s `SELECT` batch and `DELETE ... WHERE id = ANY(...)` were two independent
  autocommit statements; two concurrent purges could both select the same batch, the first
  `DELETE` would remove it, and the second `DELETE` — now affecting zero rows — still had its
  caller add the *selected* count (not the *deleted* count) to its running total. Fixed by
  combining select-and-delete into one atomic statement: `WITH batch AS (SELECT id ... FOR UPDATE
  SKIP LOCKED) DELETE ... RETURNING id`, counting only what `RETURNING` actually reports. `FOR
  UPDATE SKIP LOCKED` also means concurrent purge jobs now work on genuinely different rows in
  parallel instead of one blocking on the other's locks. The loop's termination condition changed
  from "batch shorter than the page size" to "batch empty," since `SKIP LOCKED` can legitimately
  make a batch short while expired rows still remain, just temporarily locked by another purge —
  stopping only on empty avoids leaving them for longer than necessary.
- **MEDIUM-003 — the `0003` index could not support the retention predicate it was added for.**
  `"timestamp" + make_interval(days => retention_days) < now` computes a different value per row
  (`retention_days` varies row to row), so a plain B-tree index on the bare `"timestamp"` column
  is not sargable for it — `count_expired()`/every purge batch did a full table scan despite
  `idx_audit_events_timestamp` existing, contrary to that migration's own comment. Fixed *in this
  pass* with a new migration, `0004_audit_events_expires_at`, materializing the per-row expiry
  once as a `GENERATED ALWAYS ... STORED` column with its own index — **this specific approach was
  itself found broken by the next Codex review pass; see §10's second-pass HIGH-001 for the real,
  final fix (a plain column, not generated).** `0003`'s SQL was left unchanged (already-shipped
  migrations are not edited in place — see the checksum-verification gap below) — only its
  comment's overclaim was corrected.
- **Remaining-risks item — `allow_purge` was forwardable via manifest config.** Covered above
  (§5's correction) — `app/default_factories.py`'s `postgres` `audit_sink` factory now strips
  `allow_purge` unconditionally before construction.
- **Remaining-risks item — `applied_versions()` was not actually read-only.** It called
  `_ensure_schema_migrations_table()` unconditionally, genuinely running (and committing)
  `CREATE TABLE IF NOT EXISTS` on a virgin database despite its own "read-only" docstring — `mrag
  db status` against a database nothing had ever touched needed schema `CREATE` privilege it
  should never have required. Fixed: checks `to_regclass('schema_migrations') IS NOT NULL` first
  and returns `[]` without writing anything if the table has never been created.
- **Two items the review flagged but this pass did not resolve, recorded rather than silently
  dropped:** no checksum/hash is stored per applied migration, so `MigrationRunner` cannot detect
  that an already-applied migration's `.sql` file was edited afterward — a real gap for a team
  that might edit a "shipped" migration instead of adding a new one, out of scope for this pass
  (would need a schema change to `schema_migrations` itself and a policy decision on what to do
  with a detected mismatch, not a small fix). Migration version numbers are not currently checked
  for strict sequential contiguity (a deliberately skipped number is accepted) — judged acceptable
  rather than a defect, since a version genuinely reverted before ever shipping is a legitimate
  pattern other migration tools also allow.

### 10. Second post-implementation Codex review

A follow-up premium-depth Codex review — confirming §9's five fixes actually closed their direct
scenarios, then searching specifically for regressions §9's own corrections might have
introduced — found two new HIGH defects and one new MEDIUM, all real, all introduced by §9 itself
rather than pre-existing:

- **HIGH-001 (second pass) — migration `0004` was rejected by PostgreSQL outright.** §9's
  MEDIUM-003 fix defined `expires_at` as `GENERATED ALWAYS AS ("timestamp" + make_interval(days
  => retention_days)) STORED`. PostgreSQL requires a generated column's expression to be
  IMMUTABLE; `timestamptz + interval` is declared STABLE in PostgreSQL's own catalog
  (`timestamptz_pl_interval`), because its result can depend on the session's `TimeZone` setting
  and DST transitions whenever the interval carries day/month components — which
  `make_interval(days => ...)` always does. Independently verified (not just taken on the
  review's word) against PostgreSQL's own mailing-list discussion of this exact error before
  fixing. `mrag db migrate` would have failed applying `0004` with "generation expression is not
  immutable" on every fresh database — a hard failure blocking this ADR's own core acceptance
  criterion, "démarrage sur base vide via migrations." Fixed by abandoning the generated-column
  approach entirely: `0004` now adds a **plain** `expires_at TIMESTAMPTZ` column, backfilled once
  via an ordinary `UPDATE audit_events SET expires_at = "timestamp" + make_interval(days =>
  retention_days) WHERE expires_at IS NULL` (the IMMUTABLE restriction applies only to generated-
  column expressions and index expressions, never to regular DML, so this one-time backfill can
  safely use the same STABLE arithmetic the generated column couldn't), then `SET NOT NULL`, then
  indexed. Going forward, `PostgresAuditSink.record()` computes `expires_at` in Python
  (`event.timestamp + timedelta(days=event.retention_days)`, both UTC-based per
  `AuditEvent.timestamp`'s own default field, so there is no DST/timezone ambiguity to begin with)
  and passes it as an ordinary `INSERT` value — sidestepping the IMMUTABLE-classification question
  rather than fighting it with an `AT TIME ZONE` cast (a documented workaround this pass
  considered and rejected: `timezone(text, timestamptz)` is itself STABLE for an arbitrary runtime
  zone name, so it trades one non-immutable function for another).
- **HIGH-002 (second pass) — the ledger's atomic increment was not safe to retry.** §9's HIGH-002
  fix made `record_ingested()`'s version increment atomic *inside* PostgreSQL, closing the
  concurrent-*different*-callers race — but `record_ingested()` still executed `_UPSERT_INGEST`
  through `_execute()`, which retries any connection-level failure automatically. That retry
  assumes the wrapped statement is idempotent (true for a plain `SELECT`, or `record()`'s `INSERT
  ... ON CONFLICT DO NOTHING`); it is not true for `version = document_lifecycle.version + 1`. If
  PostgreSQL executes and commits the UPSERT but the client never receives the result before the
  connection breaks — an inherently ambiguous outcome no client-side signal can distinguish from
  "never executed at all" — the automatic retry would run the same increment a second time for one
  logical call, silently producing a version gap (e.g. 3 → 5) that looks like two ingestions
  happened. Fixed by splitting the shared connection-checkout-and-classify logic (`_run_once()`)
  out from two separate callers: `_execute()` (unchanged behavior — wraps `_run_once()` in
  `retry_with_backoff`, for statements safe to repeat) and a new `_execute_once()` (goes through
  the circuit breaker only, never retries a connection-level failure). `record_ingested()` now
  calls `_execute_once()`; `tombstone()` deliberately still calls `_execute()`, since its `UPDATE`
  sets fixed values (`status`, `chunk_ids = []`, a `now` captured once before any attempt) rather
  than incrementing anything — re-running it after an ambiguous outcome produces the identical end
  state either way, so retrying it is genuinely safe and beneficial. A unit test for each
  direction (`record_ingested()` must NOT retry; `tombstone()` still DOES) makes the distinction a
  tested property, not just a comment.
- **MEDIUM-001 (second pass) — the same non-retry-safety gap existed in `purge_expired()`.**
  §9's MEDIUM-002 fix made select-and-delete one atomic `WITH ... FOR UPDATE SKIP LOCKED ...
  DELETE ... RETURNING` statement, correctly closing the concurrent-purge-jobs over-count — but
  `purge_expired()` still executed it through the same automatically-retrying `_execute()`. The
  identical ambiguous-outcome scenario applies: if a batch's `DELETE` commits but the client never
  sees `RETURNING` before the connection breaks, a retry would select and delete a *different*
  batch of still-expired rows (the first batch is already gone), and the first batch's row count
  would never be added to `total_deleted` — a real under-count of how many audit rows were
  actually removed, reintroducing in the retry path exactly the class of inaccuracy §9's
  MEDIUM-002 fix was meant to eliminate in the concurrency path. Fixed the same way: `purge_expired()`
  now calls the sink's own new `_execute_once()` instead of `_execute()`. `record()` and
  `count_expired()` are unaffected — both already used naturally retry-safe statements (`INSERT
  ... ON CONFLICT DO NOTHING`, a plain `SELECT count(*)`).
- **Remaining-risks item — the `EXPLAIN` test for MEDIUM-003 could flap independent of
  correctness.** Inserting only 200 rows and asserting the index name appears in the plan
  conflates "the index is usable" with "the planner chooses it for this specific, small dataset" —
  PostgreSQL's cost-based planner can correctly prefer a sequential scan over a perfectly usable
  index on a small table, which would make this test fail for reasons unrelated to whether the fix
  is correct (or, on a different PostgreSQL version/configuration, pass for the wrong reason).
  Fixed by wrapping the `EXPLAIN` in `SET LOCAL enable_seqscan = OFF` (scoped to one transaction,
  never touching the pool's other connections) — the standard technique for testing index
  *usability* independent of the planner's dataset-size-dependent *preference*.
- **Confirmed still closed, no regression:** the `(version, name)` migration pairing fix, `target`
  catalog validation, the ledger's cross-*different*-caller atomicity, `FOR UPDATE SKIP LOCKED`
  purge concurrency, the `allow_purge` manifest-config block, and `applied_versions()`'s genuine
  read-only behavior — this pass's own re-verification found all six still correctly closed by §9,
  with no new defect in any of them.

## Consequences

- `pyproject.toml`'s `postgres` extra becomes `psycopg[binary,pool]>=3.1` (pulls in the separate
  `psycopg-pool` PyPI package).
- Both adapters' unit tests lose their previous `adapter._conn = fake` seam (there is no more
  `self._conn`) — replaced by an injectable `pool=` constructor parameter accepting a trivial fake
  pool object exposing `.connection()` as a context manager, preserving "psycopg never needs to be
  importable for a unit test" (architecture-reviewer/test-specialist, pre-implementation).
- Migration-apply/rollback logic is unit-tested against fakes plus real `tmp_path` `.sql` files;
  the actual `CREATE`→migrate→`DROP`→rollback round-trip against a real PostgreSQL instance is
  `@pytest.mark.integration` coverage, written but **not executed** in this sandboxed environment
  or in current CI (no Postgres service container exists in `.github/workflows/ci.yml`) — the
  same "written correctly, not yet proven" honesty already established for `pg_dump`/`pg_restore`
  in `docs/refactoring/lot-16c-deployment-runbooks.md`. Adding a CI Postgres service container
  would close this gap; it is out of this lot's stated scope.
- No manifest currently wires `lifecycle_ledger: type: postgres` in any shipped preset (only
  `audit_sink: type: postgres` does, in `secure-enterprise-rag.yaml`) — this ADR does not change
  that; `PostgresLifecycleLedger` remains real, tested code reachable by any manifest that chooses
  to wire it, same as before.
- `close()` on both adapters is unchanged in its external contract (already existed, already
  correctly discovered by `Container.close()`) — only its internal body changes, from closing one
  cached connection to closing a pool.
