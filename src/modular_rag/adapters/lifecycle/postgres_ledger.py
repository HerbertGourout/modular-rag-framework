"""PostgreSQL-backed LifecycleLedger (Lot 12a, docs/refactoring-plan.md — "The
lifecycle/idempotency ledger itself is backed by PostgreSQL, consistent with
Lot 10's audit-store choice."). Connection pooling, migrations, and the
retirement of implicit runtime schema creation are ADR-0011 (PostgreSQL
migrations, connection pooling, and audit retention) — see that ADR for the
full design history and `docs/adr/_index.md` before assuming any "Lot 7"
mentioned elsewhere in this codebase's own `docs/refactoring-plan.md` (a
different, already-completed body of work — the `DocumentEngine` contract —
refers to this same number) is related to it.

`psycopg`/`psycopg_pool` are imported lazily per `.claude/.instructions.md`
§4 — not declared in `pyproject.toml`'s `v1` extra, same "opt-in
infrastructure" precedent as `adapters/audit/postgres_sink.py` (Lot 10).
Install with: `pip install "modular-rag[postgres]"` (`psycopg[binary,pool]>=3.1`).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from modular_rag.contracts.lifecycle import INDEX_SCHEMA_VERSION, DocumentRecord, DocumentStatus
from modular_rag.core.errors import ConfigurationError, StorageError
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitState,
    retry_with_backoff,
    unhealthy_dependency,
)

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

# Lot 6 (readiness and resilience): a probe-specific timeout bound for
# check_health()'s dedicated connection, separate from `self._timeout` (the
# real connection-establishment budget used by the pool) — see that
# method's docstring.
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

# ADR-0011: pool sizing defaults and an enforced upper bound. architecture-
# reviewer (pre-implementation): `max_size` is manifest-configurable via
# `**cfg.config` with no factory-level guard otherwise — a typo'd or
# malicious manifest value could exhaust the server's `max_connections`
# across this ledger, the audit sink, and every `/ready` probe's own
# separate bare connection. Validated in `__init__`, not merely documented.
_DEFAULT_POOL_MIN_SIZE = 1
_DEFAULT_POOL_MAX_SIZE = 10
_POOL_MAX_SIZE_LIMIT = 32
# test-specialist (pre-implementation): an explicit, short bound on how long
# a caller waits to check out a connection from the pool — the
# `psycopg_pool` default (30s) would otherwise compound badly with
# `retry_with_backoff`'s own attempt budget in `_execute()` below.
_POOL_CHECKOUT_TIMEOUT = 5.0


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
# `PoolClosed` added under ADR-0011 (test-specialist, pre-implementation,
# verified live against psycopg's own published source): `psycopg_pool`'s
# `PoolClosed` also subclasses `psycopg.OperationalError` and lives in a
# module whose name starts with "psycopg" — without this exclusion, calling
# any method on this ledger after `close()` would retry three times against
# a *permanently* closed pool before surfacing the real error, instead of
# failing immediately.
_NON_TRANSIENT_SUBCLASSES = frozenset(
    {"InvalidPassword", "InvalidAuthorizationSpecification", "PoolClosed"}
)


def _is_connection_level_error(exc: Exception) -> bool:
    """True for `psycopg.OperationalError`/`InterfaceError` *or a subclass
    of either*, walking the exception's full MRO by class name rather than
    an `isinstance()` check so this never needs to import `psycopg` itself
    (`_execute()`'s docstring explains why: an injected `pool=` test double
    may have no psycopg dependency at all).

    A strict exact-name match against only "OperationalError"/
    "InterfaceError" (the original version of this function) missed real
    subclasses psycopg raises for specific SQLSTATE conditions —
    `ConnectionFailure`, `ConnectionDoesNotExist`, `AdminShutdown`,
    `CrashShutdown` among others. psycopg >=3.2.4 preserves these specific
    classes on a server-side disconnect instead of collapsing them to the
    generic base, so an admin-initiated restart or crash was previously
    treated as a permanent failure: never retried, the dead connection
    never invalidated. `InvalidPassword`/`InvalidAuthorizationSpecification`/
    `PoolClosed` are explicitly excluded even though they too subclass
    `OperationalError` — see `_NON_TRANSIENT_SUBCLASSES`.

    psycopg is not installed in this dev environment to verify live
    (deliberately opt-in, lazily-imported infrastructure per this module's
    own docstring), so the class names walked here are sourced from the
    published psycopg3/psycopg_pool exception hierarchy, not introspection,
    unlike `qdrant_client.http.exceptions.ResponseHandlingException` in the
    Qdrant stores (verified live there).
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

# Codex review HIGH-002 (post-implementation): unlike `_UPSERT` above (which
# writes a caller-supplied `version` verbatim — `restore_record()`'s job,
# where the exact prior state must round-trip unchanged), this increments
# `version` atomically *inside PostgreSQL*, in the same statement as the
# write. `record_ingested()` used to read the current version with a
# separate `get()`, compute `+ 1` in Python, and write it back through a
# second, independently-pooled-and-checked-out connection — two concurrent
# calls for the same `document_key` could both read the same version, both
# compute the same next version, and the second write would silently
# overwrite the first (a lost update) rather than being ordered after it.
# `INSERT ... ON CONFLICT DO UPDATE` is atomic per row in PostgreSQL (a
# row-level lock is held for the statement's duration), so this can never
# lose an update no matter how many *different* callers race on the same
# key. `created_at` is deliberately absent from the `SET` clause: on
# conflict (an existing row), it is left untouched, preserving the original
# creation time exactly like the old read-modify-write did — only `VALUES`'
# initial-insert value is ever used for a brand new row.
#
# Codex review HIGH-002 (second post-implementation pass): atomicity against
# concurrent *different* callers is not the same guarantee as safety against
# *retrying the same call* — this statement increments rather than sets a
# fixed value, so re-running it (e.g. after a connection breaks between the
# server committing and the client receiving the result) bumps the version
# again for what is logically one call. Executed via `_execute_once()`
# (never `_execute()`'s automatic retry) for exactly this reason — see that
# method's own docstring.
_UPSERT_INGEST = """
INSERT INTO document_lifecycle
    (document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
     created_at, updated_at)
VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s)
ON CONFLICT (document_key) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    content_hash = EXCLUDED.content_hash,
    version = document_lifecycle.version + 1,
    schema_version = EXCLUDED.schema_version,
    status = EXCLUDED.status,
    chunk_ids = EXCLUDED.chunk_ids,
    updated_at = EXCLUDED.updated_at
RETURNING document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
          created_at, updated_at
"""

# Codex review HIGH-002 (post-implementation): same atomicity fix as
# `_UPSERT_INGEST` above, for `tombstone()` — a single `UPDATE ... RETURNING`
# rather than a `get()` (read) followed by a separate `_write()` (write).
# Whether the document exists is now determined by whether this statement
# affects a row (`fetchone()` returns `None` on zero matches), not by a
# preceding read that a concurrent `record_ingested()`/`tombstone()` call
# on the same key could race against.
_TOMBSTONE = """
UPDATE document_lifecycle
SET status = %s, chunk_ids = %s, updated_at = %s
WHERE document_key = %s
RETURNING document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
          created_at, updated_at
"""


class PostgresLifecycleLedger:
    """Durable `LifecycleLedger` backed by a single PostgreSQL table. Requires
    a reachable PostgreSQL instance whose schema has been migrated — see
    `adapters/postgres/migrations.py` and
    `docs/adr/0011-postgresql-migrations-pooling-and-retention.md`
    — or constructed with `auto_migrate=True` for local/dev convenience.
    See `tests/integration/test_postgres_lifecycle_ledger.py`
    (`@pytest.mark.integration`, same convention as
    `tests/integration/test_postgres_audit_sink.py`, Lot 10).
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
    ) -> None:
        if not (1 <= min_size <= max_size <= _POOL_MAX_SIZE_LIMIT):
            raise ConfigurationError(
                f"min_size={min_size!r}/max_size={max_size!r} invalid: require "
                f"1 <= min_size <= max_size <= {_POOL_MAX_SIZE_LIMIT}."
            )
        self._dsn = dsn
        # Lot 6 (readiness and resilience): harmonized with QdrantStore's/
        # QdrantSparseStore's own 30.0s default — `psycopg.connect()`
        # previously received no `connect_timeout` at all, meaning a hung
        # connection attempt could block indefinitely instead of failing
        # within a bounded time.
        self._timeout = timeout
        self._circuit = circuit_breaker or CircuitBreaker()
        self._min_size = min_size
        self._max_size = max_size
        self._auto_migrate = auto_migrate
        # ADR-0011: replaces the single cached `psycopg.Connection` +
        # per-query `threading.Lock()` this class used before — a
        # `ConnectionPool` is internally thread-safe for concurrent
        # checkout (architecture-reviewer, pre-implementation), so no query-
        # level lock is needed any more. `self._lock` is retained, narrowed
        # to guard only the lazy, one-time pool *construction* below (two
        # threads racing to create the pool for the first time must not
        # both succeed). `pool=` is directly injectable for unit tests
        # (architecture-reviewer/test-specialist, pre-implementation): the
        # previous `adapter._conn = fake` seam is gone along with
        # `self._conn`, and unit tests in this repo must not require
        # psycopg to be importable.
        self._lock = threading.Lock()
        self._pool: ConnectionPool | None = pool

    def _get_pool(self) -> ConnectionPool:
        """Caller must NOT hold `self._lock` (acquires it itself, narrowly,
        only around first-time construction). Lazy, matching every other
        adapter's `_client`/`_get_client()` convention in this codebase —
        no network I/O in `__init__`.

        If `self._auto_migrate` is set, `adapters.postgres.migrations.
        MigrationRunner.migrate()` runs first, on its own dedicated
        connection (never the pool being constructed here) — ADR-0011's
        "one schema source of truth" rule: this is the exact same migration
        runner and the exact same `.sql` files `mrag db migrate` uses, not
        a second, parallel implicit-schema mechanism. Default `False`
        (a behavior change from this ledger's previous, unconditional
        inline `CREATE TABLE IF NOT EXISTS` on every connect) — a fresh
        deployment must run migrations explicitly first; `auto_migrate=True`
        is documented as local/dev convenience only, not a production
        recommendation (see `docs/guides/postgres-permissions.md`: a
        production app role is INSERT/SELECT/UPDATE-only, without the
        CREATE privilege `auto_migrate` needs).
        """
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
        statements). Checks out one pooled connection, executes `query`,
        and classifies a connection-level failure by raising
        `_RetryableQueryError` (chaining the real cause) — it is the
        caller's job to decide whether that's worth retrying, not this
        method's.

        Classifies connection-level failures by exception class *name*
        (`_is_connection_level_error()`) rather than importing `psycopg` to
        `isinstance()`-check against it — an injected `pool=` test double
        may have no psycopg dependency at all (this repo's own unit tests
        inject one directly). architecture-reviewer (pre-implementation):
        `ConnectionPool` already disposes of and replaces a connection that
        is broken *when checked out or returned* — but a connection that
        dies *mid-query*, after this method has already borrowed it, is a
        failure the caller still needs to see classified, so the next
        attempt (if any) checks out a fresh connection rather than assuming
        the pool alone caught it.
        """
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
                # ADR-0011: with implicit schema creation retired, a
                # missing table is a real, expected-to-happen
                # misconfiguration (migrations never run), not an exotic
                # failure — give the caller an actionable hint instead of
                # only psycopg's raw "relation ... does not exist" message.
                raise StorageError(
                    f"{exc} — has the schema been migrated? Run `mrag db migrate`."
                ) from exc
            raise

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Routes a query through one retry+circuit-breaker sequence
        (Codex review HIGH-003, Lot 6), checking out a pooled connection
        per attempt rather than reusing one cached connection (ADR-0011).
        Only for statements safely repeatable end to end: `get()`,
        `list_active()`, `export_all()` (plain `SELECT`s), and
        `restore_record()`'s `_write()` (an `UPSERT` that writes a
        caller-supplied `version` verbatim — re-running it with the same
        arguments produces the same final row either way). See
        `_execute_once()` for `record_ingested()`, which this is
        deliberately NOT used for.
        """
        try:
            return self._circuit.call(
                lambda: retry_with_backoff(
                    lambda: self._run_once(query, params), retryable=(_RetryableQueryError,)
                )
            )
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def _execute_once(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Codex review HIGH-002 (second post-implementation pass): like
        `_execute()`, but never retries a connection-level failure — for a
        statement whose effect is not safe to repeat by simply running it
        again. `_UPSERT_INGEST` (the only current caller, via
        `record_ingested()`) increments `version` atomically *inside*
        PostgreSQL — safe against concurrent *different* callers (that's
        the whole point of the atomic `version = document_lifecycle.version
        + 1`), but not safe against *retrying the same logical call*: if
        PostgreSQL executes and commits the UPSERT but the client never
        receives its `RETURNING` result before the connection breaks,
        `_execute()`'s automatic retry would run `_UPSERT_INGEST` a second
        time for what is logically one `record_ingested()` call — and
        because the statement increments rather than sets a fixed value,
        that second execution bumps the version *again*, producing a gap
        (e.g. version jumps from 3 to 5) that falsely looks like two
        separate ingestions happened. Still goes through the circuit
        breaker (fails fast if already `OPEN`; records this attempt's own
        success/failure) and still checks out a fresh pooled connection —
        just never re-executes the statement itself after a connection-
        level error. The caller sees the failure immediately as a
        `StorageError`; whether to retry the whole logical
        `record_ingested()` call is a decision only that caller's own
        caller can make safely, since only it knows whether re-ingesting
        the same content is an acceptable (if version-inflating) outcome.
        """
        try:
            return self._circuit.call(lambda: self._run_once(query, params))
        except _RetryableQueryError as exc:
            raise exc.__cause__ from None  # type: ignore[misc]

    def get(self, document_key: str) -> DocumentRecord | None:
        try:
            row = self._execute(_SELECT, (document_key,)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to read document_key={document_key!r}: {exc}") from exc
        if row is None:
            return None
        return self._row_to_record(row)

    def list_active(self) -> list[DocumentRecord]:
        try:
            rows = self._execute(_SELECT_ACTIVE, (DocumentStatus.ACTIVE.value,)).fetchall()
        except Exception as exc:
            raise StorageError(f"Failed to list active documents: {exc}") from exc
        return [self._row_to_record(row) for row in rows]

    def export_all(self) -> list[DocumentRecord]:
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
        """Atomic upsert-and-increment (Codex review HIGH-002,
        post-implementation) — see `_UPSERT_INGEST`'s own comment for the
        full rationale (a lost-update race the previous read-then-write
        design was exposed to once the connection pool made genuinely
        concurrent checkouts routine). Uses `_execute_once()`, not
        `_execute()` (Codex review HIGH-002, second post-implementation
        pass) — see that method's own docstring for why an automatic retry
        of this specific statement would risk double-incrementing the
        version for a single logical call."""
        now = datetime.now().astimezone()
        try:
            row = self._execute_once(
                _UPSERT_INGEST,
                (
                    document_key,
                    tenant_id,
                    content_hash,
                    INDEX_SCHEMA_VERSION,
                    DocumentStatus.ACTIVE.value,
                    json.dumps(list(chunk_ids)),
                    now,
                    now,
                ),
            ).fetchone()
        except Exception as exc:
            raise StorageError(
                f"Failed to write document_key={document_key!r}: {exc}"
            ) from exc
        return self._row_to_record(row)

    def tombstone(self, document_key: str) -> DocumentRecord | None:
        """Atomic update (Codex review HIGH-002, post-implementation) — see
        `_TOMBSTONE`'s own comment. `None` when `document_key` doesn't
        exist, determined by the `UPDATE` itself matching zero rows, not by
        a preceding `get()` a concurrent write could race against."""
        now = datetime.now().astimezone()
        try:
            row = self._execute(
                _TOMBSTONE,
                (DocumentStatus.TOMBSTONED.value, json.dumps([]), now, document_key),
            ).fetchone()
        except Exception as exc:
            raise StorageError(
                f"Failed to tombstone document_key={document_key!r}: {exc}"
            ) from exc
        if row is None:
            return None
        return self._row_to_record(row)

    def _write(self, record: DocumentRecord) -> None:
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
        """Release the underlying connection pool, if one was ever opened.

        Same gap, same fix as `adapters/audit/postgres_sink.py::PostgresAuditSink.close()`
        (Codex review, MED-003): without this, `Container.close()`'s
        `getattr(component, "close", None)` discovery silently found nothing to call,
        leaking this ledger's connections on every `app.close()`. Idempotent.
        `self._pool` is reset to `None` (architecture-reviewer, pre-implementation),
        not merely closed — a closed `ConnectionPool` raises `PoolClosed`
        permanently, so reuse after `close()` (relied on by
        `tests/integration/test_postgres_lifecycle_ledger.py`'s fixture,
        which closes and reopens the same ledger instance across tests)
        must construct a fresh pool via `_get_pool()`, not resurrect the
        old one.
        """
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). One cheap round-trip on a dedicated, throwaway
        connection — never `self._pool`. See
        `adapters.vectorstores.qdrant_store.QdrantStore.check_health()` for
        the shared rationale (single fast attempt, no retry; reads but
        never mutates `self._circuit`), and
        `docs/adr/0010-health-checkable-and-readiness-semantics.md` §4 for
        the full history of why this method always opens its own
        connection with `statement_timeout` baked into `options=` and TCP
        keepalives, rather than ever touching shared connection state.

        ADR-0011 addition (architecture-reviewer, pre-implementation):
        retiring the inline schema auto-creation this ledger used to
        perform on every connect means a reachable-but-not-yet-migrated
        database no longer self-heals — without this check, `/ready` would
        keep reporting healthy while every real query failed with
        "relation does not exist." `SELECT 1` is replaced by
        `SELECT to_regclass('document_lifecycle') IS NOT NULL` — the same
        single query and cost, now also proving the expected table exists,
        not merely that the server answers.
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
                    "SELECT to_regclass('document_lifecycle') IS NOT NULL"
                ).fetchone()[0]
        except Exception as exc:
            # Codex review MED-002 (Lot 6): /ready is unauthenticated —
            # never put a raw exception message in the public response.
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]
        if not schema_exists:
            # ADR-0011: hand-authored, internally-known detail string, not
            # derived from an external exception — exempt from the
            # classification requirement above for the same reason
            # Qdrant's collection-validation messages are (ADR-0010 §5).
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=(
                        "schema not migrated (table document_lifecycle missing — "
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
