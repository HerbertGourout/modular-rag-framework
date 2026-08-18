"""PostgreSQL-backed AuditSink (Lot 10, docs/refactoring-plan.md — "Persist the
audit event store in PostgreSQL (append-only table, not mutated in place)").

`psycopg` is imported lazily per `.claude/.instructions.md` §4: this module is
importable without psycopg installed; only `_execute()`/`_connect_once()` need it. Not
declared in `pyproject.toml`'s `v1` extra — audit persistence is opt-in
infrastructure, not a V1 core-RAG runtime dependency. Install with
`pip install psycopg[binary]>=3.1` to use this sink.
"""
from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

from modular_rag.contracts.audit import AuditEvent
from modular_rag.core.errors import StorageError
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitState,
    retry_with_backoff,
    unhealthy_dependency,
)

if TYPE_CHECKING:
    import psycopg

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


class _RetryableQueryError(Exception):
    """See `PostgresLifecycleLedger`'s identical sentinel for the full
    rationale (Codex review HIGH-003, Lot 6)."""


# See `PostgresLifecycleLedger`'s identical constant for the full
# rationale (Codex review MED-001, Lot 6, second pass).
_NON_TRANSIENT_SUBCLASSES = frozenset({"InvalidPassword", "InvalidAuthorizationSpecification"})


def _is_connection_level_error(exc: Exception) -> bool:
    """See `PostgresLifecycleLedger`'s identical helper for the full
    rationale (Codex review HIGH-003, MED-001, Lot 6) — walks the full MRO
    by class name so a psycopg subclass like `ConnectionFailure` or
    `AdminShutdown` is still recognized as connection-level, while
    `InvalidPassword`/`InvalidAuthorizationSpecification` are explicitly
    excluded as permanent, non-retryable failures."""
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
# UPDATE/DELETE statement appears anywhere in this file. Enforcing that at
# the database-permission level (a role with INSERT/SELECT only, no
# UPDATE/DELETE grants) is a deployment concern — Lot 16c's runbooks — not
# something this adapter can guarantee purely in Python.
_DDL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    causation_id    TEXT,
    tenant_id       TEXT NOT NULL,
    actor           TEXT,
    "timestamp"     TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,
    retention_days  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation ON audit_events (correlation_id);
"""

_INSERT = """
INSERT INTO audit_events
    (id, schema_version, event_type, correlation_id, causation_id, tenant_id,
     actor, "timestamp", payload, retention_days)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""


class PostgresAuditSink:
    """Durable `AuditSink` backed by a single PostgreSQL table. Requires a
    reachable PostgreSQL instance — see `tests/integration/test_postgres_audit_sink.py`
    (`@pytest.mark.integration`, same "assumes a running local service"
    convention as `adapters/vectorstores/qdrant_store.py`'s integration tests).
    """

    def __init__(
        self, dsn: str, timeout: float = 30.0, circuit_breaker: CircuitBreaker | None = None
    ) -> None:
        self._dsn = dsn
        # Lot 6 (readiness and resilience): harmonized with QdrantStore's/
        # QdrantSparseStore's own 30.0s default — see
        # `adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`'s
        # identical addition for the full rationale (no `connect_timeout`
        # was ever passed to `psycopg.connect()` before this).
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        # Lot 6: a raw `psycopg.Connection` is not safe for concurrent
        # `execute()` calls from multiple threads — see
        # `PostgresLifecycleLedger`'s identical lock for the full
        # rationale. `RAGEngine._audit()` calls `record()` on the request
        # path, so this sink is reached exactly as concurrently as the API
        # itself is.
        self._lock = threading.Lock()
        self._conn: psycopg.Connection[Any] | None = None

    def _connect_once(self) -> None:
        """Caller must hold `self._lock`. See
        `PostgresLifecycleLedger._connect_once()` for the full rationale —
        a single, non-retrying connection attempt that `_execute()` wraps
        in one retry+circuit sequence (Codex review HIGH-003, Lot 6)."""
        import psycopg

        conn = psycopg.connect(
            self._dsn, autocommit=True, connect_timeout=max(2, round(self._timeout))
        )
        conn.execute(_DDL)
        self._conn = conn

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Caller must hold `self._lock`. See
        `PostgresLifecycleLedger._execute()` for the full rationale (Codex
        review HIGH-003, Lot 6) — every real query, cold start included,
        goes through one retry+circuit-breaker sequence, with connection
        invalidation on a connection-level failure, classified by exception
        class *name* rather than an `isinstance()` check against `psycopg`
        (so an already-cached `self._conn` that's a test double never needs
        psycopg importable at all — see the identical note there).
        `record()`'s `INSERT ... ON CONFLICT DO NOTHING` is idempotent —
        see the Lot 6 acceptance criterion "ne retry que les opérations
        sûres ou idempotentes."
        """

        def _attempt() -> Any:
            if self._conn is None:
                try:
                    self._connect_once()
                except ImportError:
                    raise  # missing dependency — not retryable, surface immediately
                except Exception as exc:
                    if _is_connection_level_error(exc):
                        raise _RetryableQueryError(str(exc)) from exc
                    raise
            conn = self._conn
            assert conn is not None
            try:
                return conn.execute(query, params) if params is not None else conn.execute(query)
            except Exception as exc:
                if _is_connection_level_error(exc):
                    self._conn = None
                    raise _RetryableQueryError(str(exc)) from exc
                raise

        try:
            return self._circuit.call(
                lambda: retry_with_backoff(_attempt, retryable=(_RetryableQueryError,))
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def record(self, event: AuditEvent) -> None:
        with self._lock:
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
                    ),
                )
            except Exception as exc:
                raise StorageError(f"Failed to record audit event {event.id}: {exc}") from exc

    async def arecord(self, event: AuditEvent) -> None:
        # No native async driver wired yet (would be psycopg's AsyncConnection) —
        # documented shortcut, not a hidden one, matching the precedent set by
        # NativeEngineAdapter's capability declarations in Lot 8.
        self.record(event)

    def close(self) -> None:
        """Release the underlying connection, if one was ever opened.

        `Container.close()` discovers this via `getattr(component, "close", None)` —
        without it, this sink's connection was never released by `app.close()` despite
        the container's own docstring promising a "best-effort graceful shutdown of
        registered resources" for every component that has a `close()` method (Codex
        review, MED-003). Idempotent: calling this more than once, or on a sink that
        never opened a connection, is a safe no-op.
        """
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). One cheap `SELECT 1` round-trip on a dedicated,
        throwaway connection. See `PostgresLifecycleLedger.check_health()`
        for the full rationale (Codex review HIGH-001, Lot 6, fifth pass):
        always a fresh connection, never the shared `self._conn`/
        `self._lock` — `statement_timeout` baked in via `options=` from the
        first query onward (no unprotected SHOW/SET window), plus
        aggressive TCP keepalive parameters bounding how long a probe can
        hang against a transport that went silent after the handshake but
        before the server could enforce anything server-side."""
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
                conn.execute("SELECT 1").fetchone()
        except Exception as exc:
            # Codex review MED-002 (Lot 6): /ready is unauthenticated —
            # never put a raw exception message in the public response.
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]
        return [
            DependencyHealth(
                name=self.name(), healthy=True, latency_ms=(time.perf_counter() - t0) * 1000
            )
        ]

    def name(self) -> str:
        return "postgres"
