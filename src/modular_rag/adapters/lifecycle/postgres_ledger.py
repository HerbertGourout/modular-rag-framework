"""PostgreSQL-backed LifecycleLedger (Lot 12a, docs/refactoring-plan.md — "The
lifecycle/idempotency ledger itself is backed by PostgreSQL, consistent with
Lot 10's audit-store choice.").

`psycopg` is imported lazily per `.claude/.instructions.md` §4 — not
declared in `pyproject.toml`, same "opt-in infrastructure" precedent as
`adapters/audit/postgres_sink.py` (Lot 10). Install with:
`pip install psycopg[binary]>=3.1`.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from modular_rag.contracts.lifecycle import INDEX_SCHEMA_VERSION, DocumentRecord, DocumentStatus
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

# Lot 6 (readiness and resilience): a probe-specific timeout bound for
# check_health()'s dedicated connection, separate from `self._timeout` (the
# real connection-establishment budget used by `_execute()`'s retrying
# path) — see that method's docstring.
_HEALTH_CHECK_TIMEOUT = 5.0
# Codex review MED-002 (Lot 6, second pass) / HIGH-001 (Lot 6, fifth pass):
# a real, server-enforced deadline for the probe query itself — see
# check_health()'s docstring for why `connect_timeout` alone doesn't cover
# this.
_HEALTH_QUERY_TIMEOUT_MS = int(_HEALTH_CHECK_TIMEOUT * 1000)
# Codex review HIGH-001 (Lot 6, fifth pass): TCP keepalive parameters for
# the probe connection — see check_health()'s docstring for why a
# server-side statement_timeout alone cannot bound a probe against a peer
# that has gone silent after the TCP handshake (no live backend process to
# enforce it). Aggressive relative to normal production traffic on purpose:
# this connection exists for one query and is torn down immediately after.
_HEALTH_KEEPALIVE_IDLE = 1
_HEALTH_KEEPALIVE_INTERVAL = 1
_HEALTH_KEEPALIVE_COUNT = 2


class _RetryableQueryError(Exception):
    """Internal-only sentinel `_execute()` raises (chaining the real cause)
    to signal `retry_with_backoff` that a query failure was connection-level
    and should be retried, without needing `psycopg`'s own exception classes
    importable at the `retryable=` parameter — see `_execute()`'s docstring
    for why that matters."""


# Codex review MED-001 (Lot 6, second pass): these subclass
# `psycopg.OperationalError` by MRO (so the walk below would otherwise
# treat them as connection-level and retryable) but represent a permanent
# authentication failure that retrying cannot fix — the same reasoning
# `ConfigurationError` is already excluded from Qdrant's retryable set for.
_NON_TRANSIENT_SUBCLASSES = frozenset({"InvalidPassword", "InvalidAuthorizationSpecification"})


def _is_connection_level_error(exc: Exception) -> bool:
    """True for `psycopg.OperationalError`/`InterfaceError` *or a subclass
    of either*, walking the exception's full MRO by class name rather than
    an `isinstance()` check so this never needs to import `psycopg` itself
    (`_execute()`'s docstring explains why: an already cached `self._conn`
    may be a test double with no psycopg dependency at all).

    A strict exact-name match against only "OperationalError"/
    "InterfaceError" (the original version of this function) missed real
    subclasses psycopg raises for specific SQLSTATE conditions —
    `ConnectionFailure`, `ConnectionDoesNotExist`, `AdminShutdown`,
    `CrashShutdown` among others. psycopg >=3.2.4 preserves these specific
    classes on a server-side disconnect instead of collapsing them to the
    generic base, so an admin-initiated restart or crash was previously
    treated as a permanent failure: never retried, the dead connection
    never invalidated. `InvalidPassword`/`InvalidAuthorizationSpecification`
    are explicitly excluded even though they too subclass
    `OperationalError` — see `_NON_TRANSIENT_SUBCLASSES`.

    psycopg is not installed in this dev environment to verify live
    (deliberately opt-in, lazily-imported infrastructure per this module's
    own docstring), so the class names walked here are sourced from the
    published psycopg3 exception hierarchy, not introspection, unlike
    `qdrant_client.http.exceptions.ResponseHandlingException` in the Qdrant
    stores (verified live there).
    """
    for cls in type(exc).__mro__:
        if cls.__name__ in _NON_TRANSIENT_SUBCLASSES:
            return False
        if cls.__module__.startswith("psycopg") and cls.__name__ in {
            "OperationalError",
            "InterfaceError",
        }:
            return True
    return False

# Mutable ledger, unlike the audit store's append-only table: a document's
# row is updated in place as its version/status changes. `updated_at` is the
# authoritative "last changed" marker; history across versions is not kept
# here — that's what the audit trail (Lot 10) is for.
_DDL = """
CREATE TABLE IF NOT EXISTS document_lifecycle (
    document_key    TEXT PRIMARY KEY,
    tenant_id       TEXT,
    content_hash    TEXT NOT NULL,
    version         INTEGER NOT NULL,
    schema_version  TEXT NOT NULL,
    status          TEXT NOT NULL,
    chunk_ids       JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_lifecycle_tenant ON document_lifecycle (tenant_id);
"""

_SELECT = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle WHERE document_key = %s
"""

_SELECT_ACTIVE = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle WHERE status = %s
"""

_SELECT_ALL = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle
"""

_UPSERT = """
INSERT INTO document_lifecycle
    (document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
     created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (document_key) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    content_hash = EXCLUDED.content_hash,
    version = EXCLUDED.version,
    schema_version = EXCLUDED.schema_version,
    status = EXCLUDED.status,
    chunk_ids = EXCLUDED.chunk_ids,
    updated_at = EXCLUDED.updated_at
"""


class PostgresLifecycleLedger:
    """Durable `LifecycleLedger` backed by a single PostgreSQL table. Requires
    a reachable PostgreSQL instance — see
    `tests/integration/test_postgres_lifecycle_ledger.py`
    (`@pytest.mark.integration`, same convention as
    `tests/integration/test_postgres_audit_sink.py`, Lot 10).
    """

    def __init__(
        self, dsn: str, timeout: float = 30.0, circuit_breaker: CircuitBreaker | None = None
    ) -> None:
        self._dsn = dsn
        # Lot 6 (readiness and resilience): harmonized with QdrantStore's/
        # QdrantSparseStore's own 30.0s default — `psycopg.connect()`
        # previously received no `connect_timeout` at all, meaning a hung
        # connection attempt could block indefinitely instead of failing
        # within a bounded time.
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        # Lot 6: a raw `psycopg.Connection` is not safe for concurrent
        # `execute()` calls from multiple threads — this ledger caches and
        # reuses exactly one, and FastAPI's sync routes run concurrently
        # across threadpool workers (confirmed relevant in this codebase:
        # `HybridRetriever`'s degraded-source tracking needed the same
        # `threading.local()` treatment, Lot 5). Every public method below
        # holds this lock for its *entire* body (connection fetch through
        # query execution) — not just around `_execute()`'s lazy-init —
        # since the connection itself, not merely its creation, is the
        # shared resource. Mirrors the existing `BM25Retriever`/
        # `RateLimitMiddleware` precedent (Lot 14) for exactly this class of
        # hazard.
        self._lock = threading.Lock()
        self._conn: psycopg.Connection[Any] | None = None

    def _connect_once(self) -> None:
        """Caller must hold `self._lock`. A single, non-retrying connection
        attempt — the raw primitive `_execute()` wraps in one retry+circuit
        sequence (Codex review HIGH-003, Lot 6): both the very first cold
        connect and a mid-life reconnect after a broken connection go
        through the exact same accounting in `_execute()`, rather than
        nesting two independent retry+circuit sequences (which would
        compound into up to attempts² connection attempts, and record
        bookkeeping on `self._circuit` twice for what is really one logical
        failure)."""
        import psycopg

        # libpq treats connect_timeout=0 (or a truncated-to-zero sub-second
        # value) as "wait indefinitely" and clamps 1 up to 2 anyway — plain
        # `int(self._timeout)` inverted the fix this was meant to provide
        # for any `timeout < 1.0` (test-specialist review, Lot 6): `round()`
        # instead of truncating, floored at libpq's own minimum of 2.
        conn = psycopg.connect(
            self._dsn, autocommit=True, connect_timeout=max(2, round(self._timeout))
        )
        conn.execute(_DDL)
        self._conn = conn

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Caller must hold `self._lock`. Routes every real query — cold
        start included — through one retry+circuit-breaker sequence, with
        connection invalidation on a connection-level failure (Codex review
        HIGH-003, Lot 6): the retry+circuit wrapping previously covered only
        the very first connect; a connection that broke *after* that — the
        ordinary production failure mode, not just a cold start — was
        retried by nothing, and its failures never reopened the circuit, so
        every request kept hitting a dead socket at full rate. Every query
        reached through this helper is idempotent (`SELECT`, or
        `UPSERT`/`INSERT ON CONFLICT`) — see the Lot 6 acceptance criterion
        "ne retry que les opérations sûres ou idempotentes."

        Classifies connection-level failures by exception class *name*
        (`_is_connection_level_error()`) rather than importing `psycopg` to
        `isinstance()`-check against it: an already-cached `self._conn` may
        be a test double with no psycopg dependency at all (this repo's own
        unit tests inject one directly to avoid needing psycopg installed),
        and importing psycopg unconditionally here broke exactly that case
        — every query against a perfectly fine fake connection failed with
        "psycopg is required" before ever reaching the fake's `execute()`.
        `psycopg` is still only ever *actually* imported inside
        `_connect_once()`, when a real connection genuinely needs to be
        established.
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
                    # Connection-level failure, not a query-level one
                    # (syntax error, constraint violation) — invalidate so
                    # the next attempt reconnects instead of repeating the
                    # same failure against a dead socket.
                    self._conn = None
                    raise _RetryableQueryError(str(exc)) from exc
                raise

        try:
            return self._circuit.call(
                lambda: retry_with_backoff(_attempt, retryable=(_RetryableQueryError,))
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def get(self, document_key: str) -> DocumentRecord | None:
        with self._lock:
            try:
                row = self._execute(_SELECT, (document_key,)).fetchone()
            except Exception as exc:
                raise StorageError(f"Failed to read document_key={document_key!r}: {exc}") from exc
        if row is None:
            return None
        return self._row_to_record(row)

    def list_active(self) -> list[DocumentRecord]:
        with self._lock:
            try:
                rows = self._execute(_SELECT_ACTIVE, (DocumentStatus.ACTIVE.value,)).fetchall()
            except Exception as exc:
                raise StorageError(f"Failed to list active documents: {exc}") from exc
        return [self._row_to_record(row) for row in rows]

    def export_all(self) -> list[DocumentRecord]:
        with self._lock:
            try:
                rows = self._execute(_SELECT_ALL).fetchall()
            except Exception as exc:
                raise StorageError(f"Failed to export document_lifecycle: {exc}") from exc
        return [self._row_to_record(row) for row in rows]

    def restore_record(self, record: DocumentRecord) -> None:
        self._write(record)

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord:
        existing = self.get(document_key)
        version = existing.version + 1 if existing else 1
        now = datetime.now(existing.updated_at.tzinfo) if existing else datetime.now().astimezone()
        record = DocumentRecord(
            document_key=document_key,
            tenant_id=tenant_id,
            content_hash=content_hash,
            version=version,
            schema_version=INDEX_SCHEMA_VERSION,
            status=DocumentStatus.ACTIVE,
            chunk_ids=list(chunk_ids),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._write(record)
        return record

    def tombstone(self, document_key: str) -> DocumentRecord | None:
        existing = self.get(document_key)
        if existing is None:
            return None
        record = existing.model_copy(
            update={
                "status": DocumentStatus.TOMBSTONED,
                "chunk_ids": [],
                "updated_at": datetime.now(existing.updated_at.tzinfo),
            }
        )
        self._write(record)
        return record

    def _write(self, record: DocumentRecord) -> None:
        with self._lock:
            try:
                self._execute(
                    _UPSERT,
                    (
                        record.document_key,
                        record.tenant_id,
                        record.content_hash,
                        record.version,
                        record.schema_version,
                        record.status.value,
                        json.dumps(record.chunk_ids),
                        record.created_at,
                        record.updated_at,
                    ),
                )
            except Exception as exc:
                raise StorageError(
                    f"Failed to write document_key={record.document_key!r}: {exc}"
                ) from exc

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> DocumentRecord:
        (
            document_key,
            tenant_id,
            content_hash,
            version,
            schema_version,
            status,
            chunk_ids,
            created_at,
            updated_at,
        ) = row
        return DocumentRecord(
            document_key=document_key,
            tenant_id=tenant_id,
            content_hash=content_hash,
            version=version,
            schema_version=schema_version,
            status=DocumentStatus(status),
            chunk_ids=list(chunk_ids),
            created_at=created_at,
            updated_at=updated_at,
        )

    def name(self) -> str:
        return "postgres"

    def close(self) -> None:
        """Release the underlying connection, if one was ever opened.

        Same gap, same fix as `adapters/audit/postgres_sink.py::PostgresAuditSink.close()`
        (Codex review, MED-003): without this, `Container.close()`'s
        `getattr(component, "close", None)` discovery silently found nothing to call,
        leaking this ledger's connection on every `app.close()`. Idempotent.
        """
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). One cheap `SELECT 1` round-trip on a dedicated,
        throwaway connection. See
        `adapters.vectorstores.qdrant_store.QdrantStore.check_health()` for
        the shared rationale (single fast attempt, no retry; reads but
        never mutates `self._circuit`).

        Codex review HIGH-001 (Lot 6, fifth pass): this used to branch on
        whether `self._conn` was already populated — a bare throwaway
        connection when cold, but the *shared, cached* connection when warm
        (under `self._lock`, with a `SHOW`/`SET`/restore dance around
        `statement_timeout` since a session-level setting can't be scoped to
        one query). That warm path had three compounding problems: (1) the
        `SHOW`/first `SET` themselves ran with no query-level bound yet
        active, so a connection whose transport had gone silent (network
        partition, dropped NAT mapping) after the original TCP handshake
        could hang the probe indefinitely, before `statement_timeout` was
        even in effect; (2) even with `statement_timeout` active, a
        server-side timeout only fires if the server's backend process is
        alive to enforce it — it cannot detect a transport that has gone
        silent client-side; (3) it mutated `self._lock`-guarded shared
        state from a probe that is not supposed to affect real traffic at
        all, whatever the outcome. This method now always opens a fresh,
        dedicated, short-lived connection for the probe — cold or warm
        makes no difference, so there is only one code path. Two changes
        close the gaps `statement_timeout` alone left open: `statement_timeout`
        is baked into the connection itself via `options=` (active for
        every statement from the first query onward, no unprotected
        SHOW/SET window), and aggressive TCP keepalive parameters
        (`_HEALTH_KEEPALIVE_IDLE`/`_INTERVAL`/`_COUNT`) bound how long the
        OS takes to notice a transport gone silent after the handshake
        succeeded, independent of anything the server enforces. Because
        this never touches `self._conn` or `self._lock`, there is nothing
        for a probe to leave in a corrupted state (resolves Codex review
        MEDIUM-001, Lot 6, fourth pass, as a side effect) and no "busy"
        verdict is possible — a live request holding `self._lock` for a
        real query no longer has any bearing on readiness.
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
