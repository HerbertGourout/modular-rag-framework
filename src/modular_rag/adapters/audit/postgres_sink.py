"""PostgreSQL-backed AuditSink (Lot 10, docs/refactoring-plan.md — "Persist the
audit event store in PostgreSQL (append-only table, not mutated in place)").
Connection pooling, migrations, and retention enforcement are ADR-0011
(PostgreSQL migrations, connection pooling, and audit retention) — see that
ADR for the full design history and `docs/adr/_index.md` before assuming any
"Lot 7" mentioned elsewhere in this codebase's own `docs/refactoring-plan.md`
(a different, already-completed body of work — the `DocumentEngine`
contract — refers to this same number) is related to it.

`psycopg`/`psycopg_pool` are imported lazily per `.claude/.instructions.md`
§4: this module is importable without either installed; only the pool/
migration/`purge_expired()` paths need them. Not declared in
`pyproject.toml`'s `v1` extra — audit persistence is opt-in infrastructure,
not a V1 core-RAG runtime dependency. Install with
`pip install "modular-rag[postgres]"` to use this sink.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from modular_rag.contracts.audit import AuditEvent
from modular_rag.core.errors import ConfigurationError, SecurityError, StorageError
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitState,
    retry_with_backoff,
    unhealthy_dependency,
)

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

log = structlog.get_logger(__name__)

# Lot 6 (readiness and resilience): see
# `adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`'s identical
# constants for the full rationale.
_HEALTH_CHECK_TIMEOUT = 5.0
# Codex review MED-002 (Lot 6, second pass) / HIGH-001 (Lot 6, fifth pass):
# see `PostgresLifecycleLedger`'s identical constant for the full rationale.
_HEALTH_QUERY_TIMEOUT_MS = int(_HEALTH_CHECK_TIMEOUT * 1000)
# Codex review HIGH-001 (Lot 6, fifth pass): see
# `PostgresLifecycleLedger`'s identical constants for the full rationale.
_HEALTH_KEEPALIVE_IDLE = 1
_HEALTH_KEEPALIVE_INTERVAL = 1
_HEALTH_KEEPALIVE_COUNT = 2

# ADR-0011: see `PostgresLifecycleLedger`'s identical constants for the full
# rationale (pool sizing bounds, checkout timeout).
_DEFAULT_POOL_MIN_SIZE = 1
_DEFAULT_POOL_MAX_SIZE = 10
_POOL_MAX_SIZE_LIMIT = 32
_POOL_CHECKOUT_TIMEOUT = 5.0

# security-specialist (pre-implementation): `purge_expired()` batches its
# DELETE rather than issuing one unbounded statement — this sink's
# connections are autocommit, so one giant DELETE is one long-held table
# lock. Small enough to keep any single batch's lock brief, large enough
# that a realistic backlog doesn't need thousands of round-trips.
_PURGE_BATCH_SIZE = 500


class _RetryableQueryError(Exception):
    """See `PostgresLifecycleLedger`'s identical sentinel for the full
    rationale (Codex review HIGH-003, Lot 6)."""


# See `PostgresLifecycleLedger`'s identical constant for the full
# rationale (Codex review MED-001, Lot 6, second pass; `PoolClosed` added
# under ADR-0011, test-specialist, pre-implementation).
_NON_TRANSIENT_SUBCLASSES = frozenset(
    {"InvalidPassword", "InvalidAuthorizationSpecification", "PoolClosed"}
)


def _is_connection_level_error(exc: Exception) -> bool:
    """See `PostgresLifecycleLedger`'s identical helper for the full
    rationale (Codex review HIGH-003, MED-001, Lot 6) — walks the full MRO
    by class name so a psycopg/psycopg_pool subclass like `ConnectionFailure`,
    `AdminShutdown`, or `PoolClosed` is classified correctly without ever
    needing `psycopg` importable (an injected `pool=` test double may have
    no psycopg dependency at all)."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _NON_TRANSIENT_SUBCLASSES:
            return False
        if cls.__module__.startswith("psycopg") and cls.__name__ in {
            "OperationalError",
            "InterfaceError",
        }:
            return True
    return False


# Append-only by design: `ON CONFLICT (id) DO NOTHING` in the INSERT below
# means a retried record() call can never overwrite an existing row, and no
# UPDATE statement appears anywhere in this file. `purge_expired()` below is
# this class's one and only DELETE — see `docs/guides/postgres-permissions.md`
# for the DB-permission-level enforcement this Python-level convention
# alone cannot guarantee: the application's normal runtime role should never
# hold DELETE at all; only a separate, higher-privileged retention-job role
# should.
#
# `expires_at` is computed in Python (`record()`, below) and passed as an
# ordinary column value — Codex review HIGH-001 (second post-implementation
# pass): an earlier version defined `expires_at` as a `GENERATED ALWAYS ...
# STORED` column computed by PostgreSQL itself
# (`"timestamp" + make_interval(days => retention_days)`), which PostgreSQL
# rejects outright — generated-column expressions must be IMMUTABLE, and
# `timestamptz + interval` is STABLE (its result can depend on the session's
# TimeZone setting and DST transitions). Computing it once in Python instead
# — `event.timestamp + timedelta(days=event.retention_days)`, both UTC-based
# per `AuditEvent.timestamp`'s own default — sidesteps the whole
# IMMUTABLE-classification question rather than fighting it with an
# `AT TIME ZONE` cast (which trades one STABLE function for another).
_INSERT = """
INSERT INTO audit_events
    (id, schema_version, event_type, correlation_id, causation_id, tenant_id,
     actor, "timestamp", payload, retention_days, expires_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""

# `retention_days > 0` guards defensively against any row written before
# `AuditEvent.retention_days` gained its `Field(ge=1)` validation (ADR-0011)
# — a `0`/negative value must never be interpreted as "already expired,"
# regardless of what `expires_at` (computed from it) would suggest.
#
# Codex review MEDIUM-003 (post-implementation): the original predicate,
# `"timestamp" + make_interval(days => retention_days) < %s`, could never be
# satisfied by a plain index on the bare `"timestamp"` column, since the
# expression's value differs per row (retention_days varies row to row) —
# `count_expired()`/every purge batch did a full table scan despite
# `idx_audit_events_timestamp` (0003) existing. `expires_at`
# (`sql/0004_audit_events_expires_at.up.sql`) materializes that same
# computation once, at write time, so a plain B-tree index on it
# (`idx_audit_events_expires_at`, 0004) genuinely supports this predicate.
_COUNT_EXPIRED = """
SELECT count(*) FROM audit_events WHERE retention_days > 0 AND expires_at < %s
"""

# Codex review MEDIUM-002 (post-implementation): select-and-delete now
# happen in ONE atomic statement instead of two independent autocommit
# statements. The previous version ran a separate `SELECT` batch then a
# `DELETE ... WHERE id = ANY(%s)` — two concurrent `purge_expired()` calls
# could both `SELECT` the same batch, the first `DELETE` would remove it,
# and the second `DELETE` (targeting already-deleted ids) would affect zero
# rows while its caller still counted `len(ids)` — the SELECT's count, not
# the DELETE's — over-reporting how many rows were actually removed.
# `FOR UPDATE SKIP LOCKED` inside the CTE also means two concurrent purge
# jobs work on genuinely different rows in parallel instead of one blocking
# on the other's row locks; the `RETURNING` clause is the only source of
# truth this method now counts from. Executed via `_execute_once()`, not
# `_execute()` (Codex review MEDIUM-001, second post-implementation pass) —
# see that method's own docstring for why an automatic retry of this
# specific statement is unsafe even though the concurrency fix above is
# correct.
_DELETE_EXPIRED_BATCH = """
WITH batch AS (
    SELECT id FROM audit_events
    WHERE retention_days > 0 AND expires_at < %s
    ORDER BY id
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
DELETE FROM audit_events
WHERE id IN (SELECT id FROM batch)
RETURNING id
"""


class PostgresAuditSink:
    """Durable `AuditSink` backed by a single PostgreSQL table. Requires a
    reachable PostgreSQL instance whose schema has been migrated — see
    `adapters/postgres/migrations.py` and
    `docs/adr/0011-postgresql-migrations-pooling-and-retention.md` — or
    constructed with `auto_migrate=True` for local/dev convenience. See
    `tests/integration/test_postgres_audit_sink.py` (`@pytest.mark.integration`,
    same "assumes a running local service" convention as
    `adapters/vectorstores/qdrant_store.py`'s integration tests).
    """

    def __init__(
        self,
        dsn: str,
        timeout: float = 30.0,
        circuit_breaker: CircuitBreaker | None = None,
        min_size: int = _DEFAULT_POOL_MIN_SIZE,
        max_size: int = _DEFAULT_POOL_MAX_SIZE,
        auto_migrate: bool = False,
        pool: ConnectionPool | None = None,
        allow_purge: bool = False,
    ) -> None:
        if not (1 <= min_size <= max_size <= _POOL_MAX_SIZE_LIMIT):
            raise ConfigurationError(
                f"min_size={min_size!r}/max_size={max_size!r} invalid: require "
                f"1 <= min_size <= max_size <= {_POOL_MAX_SIZE_LIMIT}."
            )
        self._dsn = dsn
        # Lot 6 (readiness and resilience): harmonized with QdrantStore's/
        # QdrantSparseStore's own 30.0s default — see
        # `adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`'s
        # identical addition for the full rationale.
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        self._min_size = min_size
        self._max_size = max_size
        self._auto_migrate = auto_migrate
        # ADR-0011: see `PostgresLifecycleLedger`'s identical fields for the
        # full rationale — a `ConnectionPool` replacing the single cached
        # connection + per-query lock, `self._lock` narrowed to guarding
        # only lazy pool construction, `pool=` directly injectable for
        # unit tests.
        self._lock = threading.Lock()
        self._pool: ConnectionPool | None = pool
        # security-specialist (pre-implementation, fail-closed by design):
        # `purge_expired()` refuses to run unless this was explicitly set
        # `True` at construction. The sink instance wired into the live
        # application via a manifest's `audit_sink:` block never sets
        # this — only a dedicated instance the CLI constructs from an
        # explicit `--dsn` (never the manifest) does. This makes a
        # DB-permission misconfiguration (an app-role DSN that
        # accidentally *does* have DELETE) insufficient on its own to let
        # a purge happen through the ordinary request-serving instance —
        # two independent things have to be wrong at once, not one.
        self._allow_purge = allow_purge

    def _get_pool(self) -> ConnectionPool:
        """See `PostgresLifecycleLedger._get_pool()` for the full
        rationale (lazy construction, `auto_migrate` routing through the
        shared `MigrationRunner`, `open=False` + non-blocking `.open()`)."""
        if self._pool is not None:
            return self._pool
        with self._lock:
            if self._pool is None:
                if self._auto_migrate:
                    from modular_rag.adapters.postgres.migrations import MigrationRunner

                    MigrationRunner(self._dsn).migrate()
                from psycopg_pool import ConnectionPool

                pool = ConnectionPool(
                    self._dsn,
                    open=False,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    timeout=_POOL_CHECKOUT_TIMEOUT,
                    kwargs={"connect_timeout": max(2, round(self._timeout))},
                    configure=lambda conn: setattr(conn, "autocommit", True),
                )
                pool.open(wait=False)
                self._pool = pool
            return self._pool

    def _run_once(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Caller must invoke this via `self._circuit.call(...)`, either
        directly (`_execute_once()`, no retry) or wrapped in
        `retry_with_backoff` (`_execute()`, for genuinely idempotent
        statements). Checks out one connection from the pool, executes
        `query`, and classifies a connection-level failure by raising
        `_RetryableQueryError` (chaining the real cause) — it is the
        caller's job to decide whether that classification is worth
        retrying, not this method's."""
        pool = self._get_pool()
        try:
            with pool.connection() as conn:
                if params is not None:
                    return conn.execute(query, params)
                return conn.execute(query)
        except Exception as exc:
            if _is_connection_level_error(exc):
                raise _RetryableQueryError(str(exc)) from exc
            if type(exc).__name__ == "UndefinedTable":
                # ADR-0011: see PostgresLifecycleLedger._execute() for the
                # full rationale.
                raise StorageError(
                    f"{exc} — has the schema been migrated? Run `mrag db migrate`."
                ) from exc
            raise

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """See `PostgresLifecycleLedger._execute()` for the full rationale
        (Codex review HIGH-003, Lot 6; ADR-0011's pool-per-attempt
        checkout). Only for statements safely repeatable end to end —
        `record()`'s `INSERT ... ON CONFLICT DO NOTHING` (the Lot 6
        acceptance criterion "ne retry que les opérations sûres ou
        idempotentes") and `count_expired()`'s plain `SELECT`. See
        `_execute_once()` for the statements this is deliberately NOT used
        for."""
        try:
            return self._circuit.call(
                lambda: retry_with_backoff(
                    lambda: self._run_once(query, params), retryable=(_RetryableQueryError,)
                )
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def _execute_once(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Codex review MEDIUM-001 (second post-implementation pass): like
        `_execute()`, but never retries a connection-level failure — for a
        statement whose result is not safe to re-derive by simply running
        it again. `_DELETE_EXPIRED_BATCH` (the only current caller) selects
        and deletes *whichever* rows currently match the expiry predicate;
        if PostgreSQL executes and commits the `DELETE` but the client
        never receives the `RETURNING` result before the connection breaks,
        `_execute()`'s automatic retry would silently pick up and delete a
        *different* batch on the next attempt — the first batch's row count
        is then never added to `purge_expired()`'s running total, silently
        under-reporting how many audit rows were actually removed even
        though the deletion itself was correct. Still goes through the
        circuit breaker (fails fast if already `OPEN`; records this
        attempt's own success/failure for circuit-state purposes) and still
        checks out a fresh pooled connection per call — just never
        re-executes the statement itself after a connection-level error.
        The caller sees the failure immediately (as a `StorageError`) and
        can decide whether/how to resume, rather than this method silently
        masking an ambiguous outcome as a clean, fully-counted success.
        """
        try:
            return self._circuit.call(lambda: self._run_once(query, params))
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def record(self, event: AuditEvent) -> None:
        try:
            self._execute(
                _INSERT,
                (
                    event.id,
                    event.schema_version,
                    event.event_type.value,
                    event.correlation_id,
                    event.causation_id,
                    event.tenant_id,
                    event.actor,
                    event.timestamp,
                    json.dumps(event.payload),
                    event.retention_days,
                    event.timestamp + timedelta(days=event.retention_days),
                ),
            )
        except Exception as exc:
            raise StorageError(f"Failed to record audit event {event.id}: {exc}") from exc

    async def arecord(self, event: AuditEvent) -> None:
        # No native async driver wired yet (would be psycopg's AsyncConnection) —
        # documented shortcut, not a hidden one, matching the precedent set by
        # NativeEngineAdapter's capability declarations in Lot 8.
        self.record(event)

    def count_expired(self, now: datetime | None = None) -> int:
        """Read-only: how many rows `purge_expired()` would delete right
        now, without deleting anything. Safe to run under the same
        INSERT/SELECT-only DB role real traffic uses — deliberately does
        NOT require `allow_purge=True` (security-specialist,
        pre-implementation: a dry-run/monitoring hook must not carry the
        same fail-closed gate as the destructive method, or the two get
        confused for each other)."""
        as_of = self._require_tz_aware(now)
        try:
            row = self._execute(_COUNT_EXPIRED, (as_of,)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to count expired audit events: {exc}") from exc
        return int(row[0])

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete every audit event past its `retention_days` window,
        batched (`_PURGE_BATCH_SIZE` rows per statement) so a large backlog
        does not hold one long-lived lock. Returns the total number of rows
        deleted.

        security-specialist (pre-implementation): raises `SecurityError`
        unless this instance was constructed with `allow_purge=True` — see
        `__init__`'s docstring for why this is a fail-closed Python-level
        gate, not a substitute for the DB-permission-level separation
        `docs/guides/postgres-permissions.md` documents (an app role
        without DELETE at all vs. a separate retention-job role that has
        it) — both are meant to hold at once, neither alone is considered
        sufficient.

        Intended caller: `mrag audit purge --dsn <retention-role-dsn>`
        (never `--manifest` — see that command's own docstring for why),
        run periodically by an operator or a scheduled job, not from
        in-process application code (V1 has no scheduler component).

        Codex review MEDIUM-002 (post-implementation): loops until a batch
        comes back *empty*, not merely *shorter than the page size* — with
        `FOR UPDATE SKIP LOCKED` (see `_DELETE_EXPIRED_BATCH`), a batch can
        be short because a concurrent purge call currently holds a lock on
        some of the remaining expired rows, not because none remain; those
        rows are still expired and still this job's responsibility once the
        other call releases them, so stopping only on a genuinely empty
        result avoids leaving them unprocessed for longer than necessary.
        """
        if not self._allow_purge:
            raise SecurityError(
                "PostgresAuditSink.purge_expired() refused: this instance was not "
                "constructed with allow_purge=True. This is a fail-closed guard, not "
                "an oversight — see this method's own docstring."
            )
        as_of = self._require_tz_aware(now)
        total_deleted = 0
        while True:
            try:
                deleted_ids = [
                    row[0]
                    for row in self._execute_once(
                        _DELETE_EXPIRED_BATCH, (as_of, _PURGE_BATCH_SIZE)
                    ).fetchall()
                ]
            except Exception as exc:
                raise StorageError(f"Failed to purge expired audit events: {exc}") from exc
            if not deleted_ids:
                break
            total_deleted += len(deleted_ids)
        # docs/guides/postgres-permissions.md: purge_expired() does not
        # write its own AuditEvent (would need a new AuditEventType +
        # payload-allowlist entry — a contracts/audit.py change out of this
        # lot's scope) — this structured log line is the durable record an
        # operator has instead.
        log.info("audit_purge_completed", rows_deleted=total_deleted, as_of=as_of.isoformat())
        return total_deleted

    @staticmethod
    def _require_tz_aware(now: datetime | None) -> datetime:
        """security-specialist (pre-implementation): `audit_events."timestamp"`
        is `TIMESTAMPTZ` — a naive `datetime` passed as a query parameter is
        silently coerced using the *session's* `TimeZone` setting rather
        than raising, which would make the purge cutoff wrong in a way
        nothing surfaces. Reject naive input explicitly instead."""
        if now is None:
            return datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError(
                "PostgresAuditSink.purge_expired()/count_expired() requires a "
                "timezone-aware `now` (audit_events.\"timestamp\" is TIMESTAMPTZ) — "
                f"got a naive datetime: {now!r}."
            )
        return now

    def close(self) -> None:
        """Release the underlying connection pool, if one was ever opened.

        `Container.close()` discovers this via `getattr(component, "close", None)` —
        without it, this sink's connections were never released by `app.close()` despite
        the container's own docstring promising a "best-effort graceful shutdown of
        registered resources" for every component that has a `close()` method (Codex
        review, MED-003). Idempotent. `self._pool` is reset to `None`
        (ADR-0011, architecture-reviewer, pre-implementation) — see
        `PostgresLifecycleLedger.close()`'s identical note for why a closed
        pool cannot simply be reused.
        """
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). One cheap round-trip on a dedicated, throwaway
        connection. See `PostgresLifecycleLedger.check_health()` for the
        full rationale (Codex review HIGH-001, Lot 6, fifth pass): always a
        fresh connection, never the shared pool — `statement_timeout` baked
        in via `options=` from the first query onward (no unprotected
        SHOW/SET window), plus aggressive TCP keepalive parameters bounding
        how long a probe can hang against a transport that went silent
        after the handshake but before the server could enforce anything
        server-side.

        ADR-0011 addition: see `PostgresLifecycleLedger.check_health()`'s
        identical addition for the full rationale — `SELECT 1` replaced by
        a single query that also proves `audit_events` exists, since
        implicit schema auto-creation on connect is retired this lot.
        """
        t0 = time.perf_counter()
        if self._circuit.state == CircuitState.OPEN:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail="circuit open",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        try:
            import psycopg

            probe_timeout = max(2, round(min(self._timeout, _HEALTH_CHECK_TIMEOUT)))
            with psycopg.connect(
                self._dsn,
                connect_timeout=probe_timeout,
                options=f"-c statement_timeout={_HEALTH_QUERY_TIMEOUT_MS}",
                keepalives=1,
                keepalives_idle=_HEALTH_KEEPALIVE_IDLE,
                keepalives_interval=_HEALTH_KEEPALIVE_INTERVAL,
                keepalives_count=_HEALTH_KEEPALIVE_COUNT,
            ) as conn:
                schema_exists = conn.execute(
                    "SELECT to_regclass('audit_events') IS NOT NULL"
                ).fetchone()[0]
        except Exception as exc:
            # Codex review MED-002 (Lot 6): /ready is unauthenticated —
            # never put a raw exception message in the public response.
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]
        if not schema_exists:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=(
                        "schema not migrated (table audit_events missing — "
                        "run `mrag db migrate`)"
                    ),
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        return [
            DependencyHealth(
                name=self.name(), healthy=True, latency_ms=(time.perf_counter() - t0) * 1000
            )
        ]

    def name(self) -> str:
        return "postgres"
