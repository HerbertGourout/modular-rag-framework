"""Unit tests for adapters/lifecycle/postgres_ledger.py::PostgresLifecycleLedger.
Service-free coverage using hand-built fakes rather than a real psycopg
connection/pool (same pattern as
tests/unit/adapters/vectorstores/test_qdrant_store.py's
test_close_releases_the_client_if_one_was_opened). The real round-trip
behavior of `record_ingested()`/`tombstone()` (does a value actually persist
and read back correctly) needs a live PostgreSQL and is covered by
`tests/integration/test_postgres_lifecycle_ledger.py` instead — this file
covers close()/idempotency (Codex review, MED-002), check_health()/timeout
(Lot 6, readiness and resilience), the connection-pool seam and query-retry
classification, and — since Codex review HIGH-002 (post-implementation) —
the exact SQL text `record_ingested()`/`tombstone()` issue (proving the
atomic-increment/atomic-update statement is actually what's sent, even
though proving it's race-free under real concurrency needs the integration
tier).

ADR-0011 replaced `self._conn`/a per-query `threading.Lock()` with
`psycopg_pool.ConnectionPool` — the previous `adapter._conn = fake` seam is
gone. `pool=` is a directly injectable constructor parameter instead
(architecture-reviewer/test-specialist review, pre-implementation), so
these tests still never need psycopg installed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger
from modular_rag.core.errors import ConfigurationError, StorageError
from modular_rag.core.resilience import CircuitBreaker


def _install_fake_psycopg_module(monkeypatch, connect):
    """Codex review HIGH-001 (Lot 6, fifth pass): `check_health()` always
    does a real `import psycopg; psycopg.connect(...)` — stubbed via
    `sys.modules` since `psycopg` is not installed in this dev environment."""
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)


def _install_fake_psycopg_pool_module(monkeypatch, connection_pool_cls):
    """ADR-0011: `_get_pool()`'s lazy-construction path does a real
    `from psycopg_pool import ConnectionPool` — stubbed the same way as
    `_install_fake_psycopg_module()` above, for tests that need to observe
    or control pool *construction* itself (as opposed to tests that inject
    an already-built `pool=` directly, which never reach this import)."""
    import sys
    import types

    fake_module = types.ModuleType("psycopg_pool")
    fake_module.ConnectionPool = connection_pool_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg_pool", fake_module)


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
    """One connection issued by a `_FakePool.connection()` checkout — a
    context manager standing in for the real pool's per-checkout connection
    context (architecture-reviewer/test-specialist review, pre-implementation).
    `execute()` raises if called outside the `with` block, so a unit test
    cannot pass by accident on a connection reference leaked past its
    checkout — the real pool's connection is invalid once returned too."""

    def __init__(self, executor=None, raises: Exception | None = None) -> None:
        self._checked_out = False
        self._executor = executor
        self._raises = raises

    def __enter__(self):
        self._checked_out = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self._checked_out = False
        return False  # never suppress — matches the real pool's context manager

    def execute(self, sql, params=None):
        if not self._checked_out:
            raise AssertionError("execute() called on a connection outside its `with` block")
        if self._raises is not None:
            raise self._raises
        if self._executor is not None:
            return self._executor(sql, params)
        return _FakeCursor()


class _FakePool:
    """Stands in for `psycopg_pool.ConnectionPool`. A *factory* of
    `_FakeConn` instances (test-specialist review, pre-implementation) —
    not one cached object — so a retry test can tell "the pool gave a
    different connection on the second checkout" apart from "the same
    forgiving fake just didn't complain twice"."""

    def __init__(self, connections: list[_FakeConn]) -> None:
        self._connections = list(connections)
        self.checkout_count = 0
        self.closed = False

    def connection(self, timeout=None):
        self.checkout_count += 1
        return self._connections.pop(0)

    def close(self) -> None:
        self.closed = True


def test_close_releases_the_pool_if_one_was_opened():
    pool = _FakePool([])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    ledger.close()

    assert pool.closed is True
    assert ledger._pool is None


def test_close_is_a_no_op_when_no_pool_was_ever_opened():
    PostgresLifecycleLedger(dsn="postgresql://unused/unused").close()  # must not raise


def test_close_is_idempotent():
    pool = _FakePool([])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    ledger.close()
    ledger.close()  # calling twice must not raise, second call is a no-op


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience) / ADR-0011 (pool sizing).
# ---------------------------------------------------------------------------


def test_default_timeout_is_thirty_seconds():
    assert PostgresLifecycleLedger(dsn="postgresql://unused/unused")._timeout == 30.0


@pytest.mark.parametrize(
    ("min_size", "max_size"),
    [(0, 10), (5, 3), (1, 33), (-1, 10)],
)
def test_invalid_pool_sizing_is_rejected_at_construction(min_size, max_size):
    """ADR-0011 (architecture-reviewer, pre-implementation): `min_size`/
    `max_size` are manifest-configurable (`**cfg.config`) with no other
    guard against a typo'd or malicious value exhausting the server's
    `max_connections`."""
    with pytest.raises(ConfigurationError):
        PostgresLifecycleLedger(
            dsn="postgresql://unused/unused", min_size=min_size, max_size=max_size
        )


class _FakeSchemaCursor:
    def __init__(self, schema_exists: bool) -> None:
        self._schema_exists = schema_exists

    def fetchone(self):
        return (self._schema_exists,)


class _FakeProbeConnection:
    """Stands in for `with psycopg.connect(...) as conn:` — check_health()'s
    only use of a connection, untouched by the ADR-0011 pooling change."""

    def __init__(self, *, raises: Exception | None = None, schema_exists: bool = True) -> None:
        self._raises = raises
        self._schema_exists = schema_exists
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def execute(self, sql, *args, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _FakeSchemaCursor(self._schema_exists)


def test_check_health_returns_healthy_on_a_successful_select_1(monkeypatch):
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


def test_check_health_reports_unhealthy_when_schema_not_migrated(monkeypatch):
    """ADR-0011: retiring implicit schema auto-creation means a
    reachable-but-not-yet-migrated database must be reported unhealthy —
    otherwise `/ready` would keep saying healthy while every real query
    failed with "relation does not exist"."""
    _install_fake_psycopg_module(
        monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection(schema_exists=False)
    )
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert results[0].healthy is False
    assert "migrat" in results[0].detail.lower()


def test_check_health_bakes_in_statement_timeout_via_connect_options(monkeypatch):
    """Codex review HIGH-001 (Lot 6, fifth pass): `statement_timeout` must
    be active from the very first query on the probe connection — baked
    into `options=` at connect time, not set via a separate statement after
    connecting (which would leave the connect itself, and any query before
    a separate `SET`, unprotected)."""
    captured: dict = {}

    def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeProbeConnection()

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert results[0].healthy is True
    assert "statement_timeout=5000" in captured["options"]


def test_check_health_passes_aggressive_tcp_keepalive_parameters(monkeypatch):
    """Codex review HIGH-001 (Lot 6, fifth pass): a server-side
    `statement_timeout` alone cannot bound a probe against a peer that went
    silent after the TCP handshake succeeded — no live backend process
    remains to enforce it. TCP keepalives bound detection of that
    independently of anything the server enforces."""
    captured: dict = {}

    def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeProbeConnection()

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert results[0].healthy is True
    assert captured["keepalives"] == 1
    assert captured["keepalives_idle"] >= 1
    assert captured["keepalives_interval"] >= 1
    assert captured["keepalives_count"] >= 1


def test_check_health_never_touches_the_pool(monkeypatch):
    """The prior design reused/mutated the shared connection on
    `check_health()`'s warm path (Codex review HIGH-001, Lot 6, fifth
    pass) — this method always opens its own dedicated connection, so the
    connection *pool* (ADR-0011) must be left completely untouched,
    healthy or not."""

    class _MustNotBeTouchedPool:
        def connection(self, timeout=None):
            raise AssertionError("check_health() must never use the pool")

        def close(self):
            raise AssertionError("check_health() must never close the pool")

    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    cached_pool = _MustNotBeTouchedPool()
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=cached_pool)

    results = ledger.check_health()

    assert results[0].healthy is True
    assert ledger._pool is cached_pool  # untouched


def test_check_health_returns_unhealthy_with_a_classified_detail(monkeypatch):
    """Codex review MED-002 (Lot 6): `/ready` is unauthenticated, so the raw
    exception message (which could embed hostnames, DSNs, or SDK-internal
    text) must never reach the response — only a stable code plus a
    correlation id used to look up the full detail in server-side logs."""

    def fake_connect(dsn, **kwargs):
        raise RuntimeError("connection refused")

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert results[0].healthy is False
    assert "connection refused" not in results[0].detail
    assert results[0].detail.startswith("unreachable (")


def test_check_health_skips_the_network_call_when_the_circuit_is_open(monkeypatch):
    def fake_connect(dsn, **kwargs):
        raise AssertionError("check_health() must not connect when the circuit is open")

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", circuit_breaker=breaker)

    results = ledger.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "circuit open"


# ---------------------------------------------------------------------------
# ADR-0011: pool-per-attempt checkout, query retry/classification.
# ---------------------------------------------------------------------------


def test_get_retries_and_checks_out_a_fresh_connection_after_a_connection_level_failure():
    """Codex review HIGH-003 (Lot 6) / ADR-0011: `_execute()` retries a
    query that fails with a connection-level error by checking out a fresh
    connection from the pool, rather than repeating the same failure
    against a dead one. `psycopg` is not installed in this dev environment,
    so the fake exception below carries `psycopg.OperationalError`'s real
    module/class *name* — `_is_connection_level_error()` classifies by name
    specifically so this works without the real package."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    broken = _FakeConn(raises=fake_operational_error("connection lost"))
    healthy = _FakeConn()
    pool = _FakePool([broken, healthy])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    row = ledger.get("doc-1")

    assert row is None  # the healthy fake's default cursor.fetchone() returns None
    assert pool.checkout_count == 2  # first checkout failed, second succeeded


def test_get_retries_a_psycopg_operational_error_subclass_like_adminshutdown():
    """Codex review MED-001 (Lot 6, second pass): psycopg raises specific
    subclasses of `OperationalError` for specific SQLSTATE conditions
    (`AdminShutdown`, `ConnectionFailure`, ...) rather than the generic base
    on a server-initiated disconnect (psycopg >=3.2.4) — an exact-name
    match against only "OperationalError" missed these entirely."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_admin_shutdown = type(
        "AdminShutdown", (fake_operational_error,), {"__module__": "psycopg"}
    )
    broken = _FakeConn(raises=fake_admin_shutdown("server shutting down"))
    healthy = _FakeConn()
    pool = _FakePool([broken, healthy])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    row = ledger.get("doc-1")

    assert row is None
    assert pool.checkout_count == 2


def test_get_does_not_retry_invalid_password():
    """`InvalidPassword` also subclasses `OperationalError` by MRO, but
    retrying a bad password wastes the retry budget on an error retrying
    cannot fix — explicitly excluded (Codex review MED-001)."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_invalid_password = type(
        "InvalidPassword", (fake_operational_error,), {"__module__": "psycopg"}
    )
    broken = _FakeConn(raises=fake_invalid_password("password authentication failed"))
    pool = _FakePool([broken])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        ledger.get("doc-1")

    assert pool.checkout_count == 1  # not retried


def test_get_does_not_retry_pool_closed():
    """test-specialist review (pre-implementation, ADR-0011): `psycopg_pool
    .PoolClosed` also subclasses `psycopg.OperationalError` and lives in a
    module named `psycopg_pool` (which starts with "psycopg") — without an
    explicit exclusion this would be retried 3x against a permanently
    closed pool instead of failing immediately."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_pool_closed = type(
        "PoolClosed", (fake_operational_error,), {"__module__": "psycopg_pool"}
    )
    broken = _FakeConn(raises=fake_pool_closed("the pool is closed"))
    pool = _FakePool([broken])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        ledger.get("doc-1")

    assert pool.checkout_count == 1


def test_get_raises_a_clear_storage_error_when_the_schema_is_not_migrated():
    """ADR-0011: retiring implicit schema auto-creation means a query
    against a not-yet-migrated database is an expected, not exotic,
    failure — the wrapping `StorageError` should point at the fix."""
    fake_undefined_table = type("UndefinedTable", (Exception,), {"__module__": "psycopg.errors"})
    broken = _FakeConn(raises=fake_undefined_table('relation "document_lifecycle" does not exist'))
    pool = _FakePool([broken])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError, match="mrag db migrate"):
        ledger.get("doc-1")


# ---------------------------------------------------------------------------
# ADR-0011: lazy pool construction, auto_migrate.
# ---------------------------------------------------------------------------


class _CountingFakeConnectionPool:
    """Stands in for the real `psycopg_pool.ConnectionPool` class itself
    (not one instance) — used by tests that need to observe pool
    *construction*, as opposed to tests injecting an already-built `pool=`
    directly (which never reach `_get_pool()`'s construction branch at
    all)."""

    instances: list[_CountingFakeConnectionPool] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.opened = False
        type(self).instances.append(self)

    def open(self, wait: bool = True) -> None:
        self.opened = True

    def connection(self, timeout=None):
        return _FakeConn()

    def close(self) -> None:
        pass


def test_concurrent_first_use_constructs_the_pool_exactly_once(monkeypatch):
    """ADR-0011 (architecture-reviewer, pre-implementation): `self._lock` is
    narrowed from guarding every query (the old per-connection design) to
    guarding only lazy, one-time pool *construction* — two threads racing
    the very first real call must not each construct their own pool."""
    _CountingFakeConnectionPool.instances = []
    _install_fake_psycopg_pool_module(monkeypatch, _CountingFakeConnectionPool)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: ledger.get("doc-1"), range(10)))

    assert len(_CountingFakeConnectionPool.instances) == 1


def test_pool_is_constructed_with_open_false_then_opened_non_blocking(monkeypatch):
    """ADR-0011: `psycopg_pool.ConnectionPool`'s own documented best
    practice — construct with `open=False`, open explicitly and
    non-blockingly — matching every other adapter's no-I/O-in-`__init__`
    convention in this codebase."""
    _CountingFakeConnectionPool.instances = []
    _install_fake_psycopg_pool_module(monkeypatch, _CountingFakeConnectionPool)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    ledger.get("doc-1")

    instance = _CountingFakeConnectionPool.instances[0]
    assert instance.kwargs["open"] is False
    assert instance.opened is True


def test_auto_migrate_runs_the_migration_runner_before_first_use(monkeypatch):
    migrate_calls = {"n": 0}

    class _FakeMigrationRunner:
        def __init__(self, dsn):
            self.dsn = dsn

        def migrate(self):
            migrate_calls["n"] += 1
            return []

    monkeypatch.setattr(
        "modular_rag.adapters.postgres.migrations.MigrationRunner", _FakeMigrationRunner
    )
    _install_fake_psycopg_pool_module(monkeypatch, _CountingFakeConnectionPool)
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", auto_migrate=True)

    ledger.get("doc-1")

    assert migrate_calls["n"] == 1


def test_auto_migrate_defaults_to_false_and_never_runs_migrations():
    """ADR-0011: implicit schema creation is retired by default — a caller
    must opt in explicitly (`auto_migrate=True`) for this ledger to run
    migrations on its own."""
    pool = _FakePool([_FakeConn()])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    assert ledger._auto_migrate is False


# ---------------------------------------------------------------------------
# Codex review HIGH-002 (post-implementation): record_ingested()/tombstone()
# must be a single atomic statement, not a get()-then-write() read-modify-
# write — a lost-update race the pool made routine (see each SQL constant's
# own comment in postgres_ledger.py for the full rationale). Proving the
# race is actually closed needs real concurrent PostgreSQL callers
# (tests/integration/test_postgres_lifecycle_ledger.py); these confirm the
# SQL text itself is the atomic form, and that no separate SELECT precedes
# the write.
# ---------------------------------------------------------------------------


def _fake_lifecycle_row(
    document_key="doc-1",
    tenant_id="tenant-a",
    content_hash="hash-a",
    version=1,
    status="active",
    chunk_ids=None,
):
    now = datetime.now(UTC)
    return (
        document_key,
        tenant_id,
        content_hash,
        version,
        "1.0",
        status,
        chunk_ids if chunk_ids is not None else ["c1"],
        now,
        now,
    )


def test_record_ingested_uses_a_single_atomic_upsert_that_increments_in_sql():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[_fake_lifecycle_row()])

    pool = _FakePool([_FakeConn(executor=_executor)])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    record = ledger.record_ingested("doc-1", "tenant-a", "hash-a", ["c1"])

    assert len(captured_sql) == 1  # one statement, not a SELECT followed by a write
    assert "version = document_lifecycle.version + 1" in captured_sql[0]
    assert "ON CONFLICT (document_key) DO UPDATE" in captured_sql[0]
    assert "RETURNING" in captured_sql[0]
    assert record.document_key == "doc-1"
    assert record.version == 1


def test_record_ingested_never_retries_a_connection_level_failure():
    """Codex review HIGH-002 (second post-implementation pass): unlike
    `get()`/`list_active()`/`export_all()` (safe to retry — plain
    `SELECT`s), `_UPSERT_INGEST` must NOT be retried on a connection-level
    failure — if PostgreSQL committed the atomic increment before the
    connection broke, a retry would run the increment a second time for
    one logical call, producing a version gap. Proven here the same way
    `test_get_does_not_retry_pool_closed`-style tests prove it elsewhere:
    a connection-level error must propagate after exactly ONE checkout,
    never a second, retried one."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    broken = _FakeConn(raises=fake_operational_error("connection lost"))
    pool = _FakePool([broken])  # a second checkout would raise IndexError if attempted
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        ledger.record_ingested("doc-1", "tenant-a", "hash-a", ["c1"])

    assert pool.checkout_count == 1


def test_record_ingested_upsert_never_overwrites_created_at_on_conflict():
    """The `SET` clause must not list `created_at` — on conflict (an
    existing row), leaving it out of `SET` is what preserves the original
    creation time; explicitly setting it to the new call's timestamp would
    silently rewrite history on every re-ingestion."""
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[_fake_lifecycle_row(version=2)])

    pool = _FakePool([_FakeConn(executor=_executor)])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    ledger.record_ingested("doc-1", "tenant-a", "hash-a", ["c1"])

    set_clause = captured_sql[0].split("DO UPDATE SET", 1)[1].split("RETURNING", 1)[0]
    assert "created_at" not in set_clause


def test_tombstone_uses_a_single_atomic_update():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[_fake_lifecycle_row(status="tombstoned", chunk_ids=[])])

    pool = _FakePool([_FakeConn(executor=_executor)])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    record = ledger.tombstone("doc-1")

    assert len(captured_sql) == 1  # one statement, not a preceding get()
    assert captured_sql[0].strip().upper().startswith("UPDATE DOCUMENT_LIFECYCLE")
    assert "RETURNING" in captured_sql[0]
    assert record.status.value == "tombstoned"
    assert record.chunk_ids == []


def test_tombstone_returns_none_when_the_update_matches_no_row():
    """A document_key that doesn't exist: the UPDATE affects zero rows, and
    that (not a preceding get()) is what None is derived from."""
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    record = ledger.tombstone("does-not-exist")

    assert record is None


def test_tombstone_still_retries_a_connection_level_failure():
    """Unlike `record_ingested()` (Codex review HIGH-002, second
    post-implementation pass — deliberately non-retrying, see
    `_execute_once()`'s docstring), `_TOMBSTONE` sets fixed values
    (`status`, `chunk_ids = []`, a `now` captured once before any attempt)
    rather than incrementing anything — re-running it after an ambiguous
    connection failure produces the exact same end state either way, so it
    stays on `_execute()`'s retrying path. This is the control case proving
    that distinction is deliberate, not an oversight: a connection-level
    failure here must still succeed on retry, unlike record_ingested()'s
    equivalent test."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    broken = _FakeConn(raises=fake_operational_error("connection lost"))
    healthy = _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[_fake_lifecycle_row()]))
    pool = _FakePool([broken, healthy])
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused", pool=pool)

    record = ledger.tombstone("doc-1")  # must not raise -- retries and succeeds

    assert pool.checkout_count == 2
    assert record is not None
