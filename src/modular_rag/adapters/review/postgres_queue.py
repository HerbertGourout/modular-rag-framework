"""PostgreSQL-backed ReviewQueue (Batch 14, ADR-0014). Mirrors
`adapters.audit.postgres_sink.PostgresAuditSink`'s pool/circuit-breaker/
retry/retention shape, and `adapters.lifecycle.postgres_ledger.
PostgresLifecycleLedger`'s atomic `UPDATE ... RETURNING` pattern for
`resolve()` — a review item, unlike an audit event or a feedback record, is
genuinely mutable (a human resolves it after the fact). See those two files'
own docstrings for the detailed rationale behind each mechanism below.

`psycopg`/`psycopg_pool` are imported lazily per `.claude/.instructions.md`
§4. Install with: `pip install "modular-rag[postgres]"`.
"""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from modular_rag.contracts.review import ReviewItem
from modular_rag.core.errors import ConfigurationError, ModularRAGError, SecurityError, StorageError
from modular_rag.core.models.answer import Answer
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


_INSERT = """
INSERT INTO review_items
    (id, answer_id, query_id, tenant_id, reason, confidence, created_at,
     resolved, approved, reviewer, retention_days, expires_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""

# Atomic compare-and-set UPDATE...RETURNING (same pattern as
# PostgresLifecycleLedger's _TOMBSTONE, extended with a state guard):
# `AND resolved = FALSE` makes this a terminal transition — a second
# resolve() call against an already-resolved id affects zero rows instead
# of silently overwriting `approved`/`reviewer` a second time. Whether the
# item exists *and is pending* is determined by whether this single
# statement affects a row, not by a preceding read a concurrent resolve()
# call on the same id could race against.
#
# Codex review pass 1, HIGH-002: an earlier version omitted `AND resolved =
# FALSE`, so two reviewers (or a retried call) could approve then reject
# the same item, with the later call winning silently and no record of the
# first decision. `HumanReviewGate.resolve()` (the in-memory reference
# implementation) had the identical defect and is fixed the same way, so
# the two `ReviewQueue` implementations stay behaviorally interchangeable
# — not diverging in exactly the property a manifest-level swap between
# them must preserve.
_RESOLVE = """
UPDATE review_items
SET resolved = TRUE, approved = %s, reviewer = %s
WHERE id = %s AND resolved = FALSE
RETURNING id
"""

_SELECT_PENDING = """
SELECT id, answer_id, query_id, tenant_id, reason, confidence, created_at,
       resolved, approved, reviewer, retention_days
FROM review_items WHERE resolved = FALSE
"""

_COUNT_RESOLVED = "SELECT count(*) FROM review_items WHERE resolved = TRUE"

_COUNT_EXPIRED = """
SELECT count(*) FROM review_items WHERE retention_days > 0 AND expires_at < %s
"""

_DELETE_EXPIRED_BATCH = """
WITH batch AS (
    SELECT id FROM review_items
    WHERE retention_days > 0 AND expires_at < %s
    ORDER BY id
    LIMIT %s
    FOR UPDATE SKIP LOCKED
)
DELETE FROM review_items
WHERE id IN (SELECT id FROM batch)
RETURNING id
"""


class PostgresReviewQueue:
    """Durable `ReviewQueue` backed by a single PostgreSQL table. Requires a
    reachable PostgreSQL instance whose schema has been migrated (or
    `auto_migrate=True` for local/dev). `should_review()` is a pure,
    in-memory confidence-threshold check — identical to `HumanReviewGate`'s
    — so it never adds a DB round-trip to `RAGEngine.answer()`'s hot path;
    only `enqueue()`/`resolve()` touch the database. See
    `docs/adr/0014-feedback-drift-and-human-review.md`.
    """

    def __init__(
        self,
        dsn: str,
        threshold: float = 0.7,
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
        self._threshold = threshold
        self._dsn = dsn
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        self._min_size = min_size
        self._max_size = max_size
        self._auto_migrate = auto_migrate
        self._lock = threading.Lock()
        self._pool: ConnectionPool | None = pool
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
        try:
            return self._circuit.call(
                lambda: retry_with_backoff(
                    lambda: self._run_once(query, params), retryable=(_RetryableQueryError,)
                )
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def _execute_once(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Never retries a connection-level failure. Used for `_RESOLVE` (an
        UPDATE whose `RETURNING` result must not be silently re-derived) and
        `_DELETE_EXPIRED_BATCH` — see `PostgresLifecycleLedger._execute_once()`."""
        try:
            return self._circuit.call(lambda: self._run_once(query, params))
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def should_review(self, answer: Answer) -> bool:
        return answer.confidence is not None and answer.confidence < self._threshold

    def enqueue(self, item: ReviewItem) -> None:
        try:
            self._execute(
                _INSERT,
                (
                    item.id,
                    item.answer_id,
                    item.query_id,
                    item.tenant_id,
                    item.reason,
                    item.confidence,
                    item.created_at,
                    item.resolved,
                    item.approved,
                    item.reviewer,
                    item.retention_days,
                    item.created_at + timedelta(days=item.retention_days),
                ),
            )
        except Exception as exc:
            raise StorageError(f"Failed to enqueue review item {item.id}: {exc}") from exc

    def resolve(self, item_id: str, *, approved: bool, reviewer: str) -> None:
        try:
            row = self._execute_once(_RESOLVE, (approved, reviewer, item_id)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to resolve review item {item_id}: {exc}") from exc
        if row is None:
            raise ModularRAGError(f"No pending review item with id={item_id!r}.")

    @property
    def pending(self) -> list[ReviewItem]:
        """Live query, matching `HumanReviewGate.pending`'s "current
        snapshot" semantics — not cached, so this reflects concurrent
        resolutions immediately."""
        try:
            rows = self._execute(_SELECT_PENDING).fetchall()
        except Exception as exc:
            raise StorageError(f"Failed to list pending review items: {exc}") from exc
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: tuple[Any, ...]) -> ReviewItem:
        (
            id_, answer_id, query_id, tenant_id, reason, confidence, created_at,
            resolved, approved, reviewer, retention_days,
        ) = row
        return ReviewItem(
            id=id_, answer_id=answer_id, query_id=query_id, tenant_id=tenant_id,
            reason=reason, confidence=confidence, created_at=created_at,
            resolved=resolved, approved=approved, reviewer=reviewer,
            retention_days=retention_days,
        )

    def count_resolved(self) -> int:
        """Not part of `ReviewQueue`'s Protocol — a concrete-only read
        method for `scripts/run_drift_check.py`'s escalation metrics."""
        try:
            row = self._execute(_COUNT_RESOLVED).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to count resolved review items: {exc}") from exc
        return int(row[0])

    def count_expired(self, now: datetime | None = None) -> int:
        """Read-only — does not require `allow_purge=True`."""
        as_of = self._require_tz_aware(now)
        try:
            row = self._execute(_COUNT_EXPIRED, (as_of,)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to count expired review items: {exc}") from exc
        return int(row[0])

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete every review item past its `retention_days` window,
        batched. Raises `SecurityError` unless `allow_purge=True` — see
        `PostgresAuditSink.purge_expired()`'s docstring for the full
        fail-closed rationale. Intended caller: `mrag review purge --dsn
        <retention-role-dsn>`. Deletes resolved *and* unresolved items past
        the window alike — retention is a data-age policy, not a
        resolution-status one."""
        if not self._allow_purge:
            raise SecurityError(
                "PostgresReviewQueue.purge_expired() refused: this instance was not "
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
                raise StorageError(f"Failed to purge expired review items: {exc}") from exc
            if not deleted_ids:
                break
            total_deleted += len(deleted_ids)
        log.info("review_purge_completed", rows_deleted=total_deleted, as_of=as_of.isoformat())
        return total_deleted

    @staticmethod
    def _require_tz_aware(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError(
                "PostgresReviewQueue.purge_expired()/count_expired() requires a "
                f"timezone-aware `now` — got a naive datetime: {now!r}."
            )
        return now

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` per
        `.claude/rules/health-checks.md`'s 11 invariants. See
        `PostgresAuditSink.check_health()` for the full rationale."""
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
                    "SELECT to_regclass('review_items') IS NOT NULL"
                ).fetchone()[0]
        except Exception as exc:
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]
        if not schema_exists:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=(
                        "schema not migrated (table review_items missing — "
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
