"""PostgreSQL-backed FeedbackSink (Batch 14, ADR-0014). Mirrors
`adapters.audit.postgres_sink.PostgresAuditSink` closely — same pool/
circuit-breaker/retry shape, same append-only + retention/purge design, same
`check_health()` invariants (`.claude/rules/health-checks.md`). See that
file's own docstrings for the detailed rationale behind each mechanism below
(connection pooling, retryable-error classification, purge batching,
timezone handling) — not repeated verbatim here to avoid duplicating a
maintenance burden across two files that must already stay in lock-step.

`psycopg`/`psycopg_pool` are imported lazily per `.claude/.instructions.md`
§4 — not declared in `pyproject.toml`'s `v1` extra, same "opt-in
infrastructure" precedent as `PostgresAuditSink`. Install with:
`pip install "modular-rag[postgres]"`.
"""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from modular_rag.contracts.feedback import Feedback, FeedbackRating
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

_HEALTH_CHECK_TIMEOUT = 5.0
_HEALTH_QUERY_TIMEOUT_MS = int(_HEALTH_CHECK_TIMEOUT * 1000)
_HEALTH_KEEPALIVE_IDLE = 1
_HEALTH_KEEPALIVE_INTERVAL = 1
_HEALTH_KEEPALIVE_COUNT = 2

_DEFAULT_POOL_MIN_SIZE = 1
_DEFAULT_POOL_MAX_SIZE = 10
_POOL_MAX_SIZE_LIMIT = 32
_POOL_CHECKOUT_TIMEOUT = 5.0

_PURGE_BATCH_SIZE = 500


class _RetryableQueryError(Exception):
    """See `PostgresAuditSink`'s identical sentinel."""


_NON_TRANSIENT_SUBCLASSES = frozenset(
    {"InvalidPassword", "InvalidAuthorizationSpecification", "PoolClosed"}
)


def _is_connection_level_error(exc: Exception) -> bool:
    """See `PostgresAuditSink`'s identical helper."""
    for cls in type(exc).__mro__:
        if cls.__name__ in _NON_TRANSIENT_SUBCLASSES:
            return False
        if cls.__module__.startswith("psycopg") and cls.__name__ in {
            "OperationalError",
            "InterfaceError",
        }:
            return True
    return False


# Append-only: `ON CONFLICT (COALESCE(tenant_id, ''), idempotency_key) DO
# NOTHING` means a retried `record()` call for the same tenant's
# `Feedback.idempotency_key` never writes a second row and never raises —
# `FeedbackSink.record()`'s idempotency contract, satisfied at the storage
# layer. The conflict target is scoped per tenant, not a bare
# `idempotency_key` alone, so one tenant cannot pre-claim another tenant's
# key (see 0005_feedback.up.sql's matching `ux_feedback_tenant_idempotency`
# expression index — the ON CONFLICT target must match it exactly).
# `expires_at` is computed in Python (`record()`, below), not as a
# GENERATED column — see `PostgresAuditSink`'s identical note on why
# (`timestamptz + interval` is STABLE, not IMMUTABLE).
_INSERT = """
INSERT INTO feedback
    (id, schema_version, trace_id, tenant_id, rating, correction_text,
     citation_count, idempotency_key, submitted_by, is_test, retention_days,
     expires_at, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (COALESCE(tenant_id, ''), idempotency_key) DO NOTHING
"""

_COUNT_EXPIRED = """
SELECT count(*) FROM feedback WHERE retention_days > 0 AND expires_at < %s
"""

_SELECT_SINCE = """
SELECT id, schema_version, trace_id, tenant_id, rating, correction_text,
       citation_count, idempotency_key, submitted_by, is_test, retention_days,
       created_at
FROM feedback WHERE created_at >= %s
"""

_SELECT_ONE_BY_KEY = """
SELECT id, schema_version, trace_id, tenant_id, rating, correction_text,
       citation_count, idempotency_key, submitted_by, is_test, retention_days,
       created_at
FROM feedback WHERE COALESCE(tenant_id, '') = COALESCE(%s, '') AND idempotency_key = %s
"""

_SELECT_ALL = """
SELECT id, schema_version, trace_id, tenant_id, rating, correction_text,
       citation_count, idempotency_key, submitted_by, is_test, retention_days,
       created_at
FROM feedback
"""

_DELETE_EXPIRED_BATCH = """
WITH batch AS (
    SELECT id FROM feedback
    WHERE retention_days > 0 AND expires_at < %s
    ORDER BY id
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
DELETE FROM feedback
WHERE id IN (SELECT id FROM batch)
RETURNING id
"""


class PostgresFeedbackSink:
    """Durable `FeedbackSink` backed by a single PostgreSQL table. Requires a
    reachable PostgreSQL instance whose schema has been migrated (or
    `auto_migrate=True` for local/dev). See `docs/adr/0011-postgresql-
    migrations-pooling-and-retention.md` and `docs/adr/0014-feedback-drift-
    and-human-review.md`.
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
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        self._min_size = min_size
        self._max_size = max_size
        self._auto_migrate = auto_migrate
        self._lock = threading.Lock()
        self._pool: ConnectionPool | None = pool
        # See `PostgresAuditSink.__init__`'s identical field for the full
        # fail-closed rationale: the manifest-wired instance never sets this;
        # only a dedicated CLI-constructed instance does.
        self._allow_purge = allow_purge

    def _get_pool(self) -> ConnectionPool:
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
                raise StorageError(
                    f"{exc} — has the schema been migrated? Run `mrag db migrate`."
                ) from exc
            raise

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Safe for statements repeatable end to end — `record()`'s
        `INSERT ... ON CONFLICT DO NOTHING` and `count_expired()`'s plain
        `SELECT`. See `PostgresAuditSink._execute()`."""
        try:
            return self._circuit.call(
                lambda: retry_with_backoff(
                    lambda: self._run_once(query, params), retryable=(_RetryableQueryError,)
                )
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def _execute_once(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Never retries a connection-level failure — for `_DELETE_EXPIRED_
        BATCH`, whose `RETURNING` result must not be silently re-derived by
        a second execution. See `PostgresAuditSink._execute_once()`."""
        try:
            return self._circuit.call(lambda: self._run_once(query, params))
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def record(self, feedback: Feedback) -> None:
        try:
            self._execute(
                _INSERT,
                (
                    feedback.id,
                    feedback.schema_version,
                    feedback.trace_id,
                    feedback.tenant_id,
                    feedback.rating.value if feedback.rating is not None else None,
                    feedback.correction_text,
                    feedback.citation_count,
                    feedback.idempotency_key,
                    feedback.submitted_by,
                    feedback.is_test,
                    feedback.retention_days,
                    feedback.created_at + timedelta(days=feedback.retention_days),
                    feedback.created_at,
                ),
            )
        except Exception as exc:
            raise StorageError(f"Failed to record feedback {feedback.id}: {exc}") from exc

    async def arecord(self, feedback: Feedback) -> None:
        # No native async driver wired yet — see PostgresAuditSink.arecord().
        self.record(feedback)

    def list_since(self, since: datetime | None = None) -> list[Feedback]:
        """Not part of `FeedbackSink`'s Protocol — a concrete-only read
        method for `scripts/run_drift_check.py`, mirroring
        `InMemoryFeedbackSink.list_since()`."""
        query, params = (_SELECT_ALL, None) if since is None else (_SELECT_SINCE, (since,))
        try:
            rows = self._execute(query, params).fetchall()
        except Exception as exc:
            raise StorageError(f"Failed to list feedback: {exc}") from exc
        return [self._row_to_feedback(row) for row in rows]

    def get(self, tenant_id: str | None, idempotency_key: str) -> Feedback | None:
        """Not part of `FeedbackSink`'s Protocol — concrete-only, mirrors
        `InMemoryFeedbackSink.get()`. Used by `RAGEngine.record_feedback()`
        to return the record actually stored (not a freshly-constructed
        retry object with a different `id`) on an idempotent retry (Codex
        review pass 1, MEDIUM-001)."""
        try:
            row = self._execute(_SELECT_ONE_BY_KEY, (tenant_id, idempotency_key)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to look up feedback by idempotency key: {exc}") from exc
        return self._row_to_feedback(row) if row is not None else None

    @staticmethod
    def _row_to_feedback(row: tuple[Any, ...]) -> Feedback:
        (
            id_, schema_version, trace_id, tenant_id, rating, correction_text,
            citation_count, idempotency_key, submitted_by, is_test, retention_days,
            created_at,
        ) = row
        return Feedback(
            id=id_, schema_version=schema_version, trace_id=trace_id, tenant_id=tenant_id,
            rating=FeedbackRating(rating) if rating is not None else None,
            correction_text=correction_text, citation_count=citation_count,
            idempotency_key=idempotency_key, submitted_by=submitted_by, is_test=is_test,
            retention_days=retention_days, created_at=created_at,
        )

    def count_expired(self, now: datetime | None = None) -> int:
        """Read-only — does not require `allow_purge=True`. See
        `PostgresAuditSink.count_expired()`."""
        as_of = self._require_tz_aware(now)
        try:
            row = self._execute(_COUNT_EXPIRED, (as_of,)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to count expired feedback: {exc}") from exc
        return int(row[0])

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete every feedback record past its `retention_days` window,
        batched. Raises `SecurityError` unless `allow_purge=True` was set at
        construction — see `PostgresAuditSink.purge_expired()`'s docstring
        for the full fail-closed rationale and `docs/guides/postgres-
        permissions.md` for the DB-role-separation half of this same
        defense-in-depth pair. Intended caller: `mrag feedback purge --dsn
        <retention-role-dsn>`."""
        if not self._allow_purge:
            raise SecurityError(
                "PostgresFeedbackSink.purge_expired() refused: this instance was not "
                "constructed with allow_purge=True."
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
                raise StorageError(f"Failed to purge expired feedback: {exc}") from exc
            if not deleted_ids:
                break
            total_deleted += len(deleted_ids)
        log.info("feedback_purge_completed", rows_deleted=total_deleted, as_of=as_of.isoformat())
        return total_deleted

    @staticmethod
    def _require_tz_aware(now: datetime | None) -> datetime:
        """See `PostgresAuditSink._require_tz_aware()`."""
        if now is None:
            return datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError(
                "PostgresFeedbackSink.purge_expired()/count_expired() requires a "
                f"timezone-aware `now` — got a naive datetime: {now!r}."
            )
        return now

    def close(self) -> None:
        """Discovered via `getattr(component, "close", None)` by
        `Container.close()`. Idempotent. See `PostgresAuditSink.close()`."""
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` per
        `.claude/rules/health-checks.md`'s 11 invariants — one cheap,
        read-only round-trip on a dedicated, throwaway connection, never the
        shared pool. See `PostgresAuditSink.check_health()` for the full
        rationale behind every parameter below."""
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
                    "SELECT to_regclass('feedback') IS NOT NULL"
                ).fetchone()[0]
        except Exception as exc:
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]
        if not schema_exists:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=(
                        "schema not migrated (table feedback missing — run `mrag db migrate`)"
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
