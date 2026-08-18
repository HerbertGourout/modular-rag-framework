"""Unit tests for adapters/audit/postgres_sink.py::PostgresAuditSink.
Service-free coverage using hand-built fakes rather than a real psycopg
connection/pool (same pattern as
tests/unit/adapters/vectorstores/test_qdrant_store.py's
test_close_releases_the_client_if_one_was_opened). Everything needing a real
DDL/insert round-trip (record(), append-only behavior) needs a live
PostgreSQL and is covered by tests/integration/test_postgres_audit_sink.py
instead — this file exists for close()/idempotency (Codex review, MED-002),
check_health()/timeout (Lot 6, readiness and resilience), and, since
ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention),
the connection-pool seam, query-retry classification, and retention
(purge_expired()/count_expired()).

ADR-0011 replaced `self._conn`/a per-query `threading.Lock()` with
`psycopg_pool.ConnectionPool` — the previous `adapter._conn = fake` seam is
gone. `pool=` is a directly injectable constructor parameter instead
(architecture-reviewer/test-specialist review, pre-implementation), so
these tests still never need psycopg installed.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
from modular_rag.contracts.audit import AuditEvent, AuditEventType
from modular_rag.core.errors import ConfigurationError, SecurityError, StorageError
from modular_rag.core.resilience import CircuitBreaker


def _install_fake_psycopg_module(monkeypatch, connect):
    """Codex review HIGH-001 (Lot 6, fifth pass): see
    `PostgresLifecycleLedger`'s identical helper for the full rationale —
    `check_health()` always does a real `import psycopg;
    psycopg.connect(...)`, stubbed here via `sys.modules` since `psycopg`
    is not installed in this dev environment."""
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)


def _install_fake_psycopg_pool_module(monkeypatch, connection_pool_cls):
    """ADR-0011: see `PostgresLifecycleLedger`'s identical helper for the
    full rationale."""
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
    """See `PostgresLifecycleLedger`'s identical fake for the full
    rationale (architecture-reviewer/test-specialist review,
    pre-implementation) — a factory-issued, checkout-scoped connection
    standing in for the real pool's per-checkout context."""

    def __init__(self, executor=None, raises: Exception | None = None) -> None:
        self._checked_out = False
        self._executor = executor
        self._raises = raises

    def __enter__(self):
        self._checked_out = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self._checked_out = False
        return False

    def execute(self, sql, params=None):
        if not self._checked_out:
            raise AssertionError("execute() called on a connection outside its `with` block")
        if self._raises is not None:
            raise self._raises
        if self._executor is not None:
            return self._executor(sql, params)
        return _FakeCursor()


class _FakePool:
    """See `PostgresLifecycleLedger`'s identical fake for the full
    rationale — a *factory* of `_FakeConn` instances, not one cached
    object."""

    def __init__(self, connections: list[_FakeConn]) -> None:
        self._connections = list(connections)
        self.checkout_count = 0
        self.closed = False

    def connection(self, timeout=None):
        self.checkout_count += 1
        return self._connections.pop(0)

    def close(self) -> None:
        self.closed = True


def _event(**overrides: object) -> AuditEvent:
    defaults: dict[str, object] = {
        "event_type": AuditEventType.RUN_SUCCEEDED,
        "correlation_id": "c1",
        "tenant_id": "t1",
    }
    defaults.update(overrides)
    return AuditEvent(**defaults)  # type: ignore[arg-type]


def test_close_releases_the_pool_if_one_was_opened():
    pool = _FakePool([])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    sink.close()

    assert pool.closed is True
    assert sink._pool is None


def test_close_is_a_no_op_when_no_pool_was_ever_opened():
    PostgresAuditSink(dsn="postgresql://unused/unused").close()  # must not raise


def test_close_is_idempotent():
    pool = _FakePool([])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    sink.close()
    sink.close()  # calling twice must not raise, second call is a no-op


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience) / ADR-0011 (pool sizing).
# ---------------------------------------------------------------------------


def test_default_timeout_is_thirty_seconds():
    assert PostgresAuditSink(dsn="postgresql://unused/unused")._timeout == 30.0


@pytest.mark.parametrize(
    ("min_size", "max_size"),
    [(0, 10), (5, 3), (1, 33), (-1, 10)],
)
def test_invalid_pool_sizing_is_rejected_at_construction(min_size, max_size):
    """ADR-0011: see `PostgresLifecycleLedger`'s identical test for the
    full rationale (architecture-reviewer review, pre-implementation)."""
    with pytest.raises(ConfigurationError):
        PostgresAuditSink(dsn="postgresql://unused/unused", min_size=min_size, max_size=max_size)


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
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


def test_check_health_reports_unhealthy_when_schema_not_migrated(monkeypatch):
    """ADR-0011: see `PostgresLifecycleLedger`'s identical test for the
    full rationale."""
    _install_fake_psycopg_module(
        monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection(schema_exists=False)
    )
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is False
    assert "migrat" in results[0].detail.lower()


def test_check_health_bakes_in_statement_timeout_via_connect_options(monkeypatch):
    """Codex review HIGH-001 (Lot 6, fifth pass): see
    `PostgresLifecycleLedger`'s identical test for the full rationale."""
    captured: dict = {}

    def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeProbeConnection()

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is True
    assert "statement_timeout=5000" in captured["options"]


def test_check_health_passes_aggressive_tcp_keepalive_parameters(monkeypatch):
    """Codex review HIGH-001 (Lot 6, fifth pass): see
    `PostgresLifecycleLedger`'s identical test for the full rationale."""
    captured: dict = {}

    def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeProbeConnection()

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is True
    assert captured["keepalives"] == 1
    assert captured["keepalives_idle"] >= 1
    assert captured["keepalives_interval"] >= 1
    assert captured["keepalives_count"] >= 1


def test_check_health_never_touches_the_pool(monkeypatch):
    """See `PostgresLifecycleLedger`'s identical test for the full
    rationale — a pool cached from real `record()` traffic must be left
    completely untouched."""

    class _MustNotBeTouchedPool:
        def connection(self, timeout=None):
            raise AssertionError("check_health() must never use the pool")

        def close(self):
            raise AssertionError("check_health() must never close the pool")

    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    cached_pool = _MustNotBeTouchedPool()
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=cached_pool)

    results = sink.check_health()

    assert results[0].healthy is True
    assert sink._pool is cached_pool


def test_check_health_returns_unhealthy_with_a_classified_detail(monkeypatch):
    """Codex review MED-002 (Lot 6): see `PostgresLifecycleLedger`'s
    identical test for the rationale — `/ready` is unauthenticated."""

    def fake_connect(dsn, **kwargs):
        raise RuntimeError("connection refused")

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

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
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", circuit_breaker=breaker)

    results = sink.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "circuit open"


# ---------------------------------------------------------------------------
# ADR-0011: pool-per-attempt checkout, query retry/classification.
# ---------------------------------------------------------------------------


def test_record_retries_and_checks_out_a_fresh_connection_after_a_connection_level_failure():
    """Codex review HIGH-003 (Lot 6) / ADR-0011: see
    `PostgresLifecycleLedger`'s identical test for the full rationale."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    broken = _FakeConn(raises=fake_operational_error("connection lost"))
    healthy = _FakeConn()
    pool = _FakePool([broken, healthy])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    sink.record(_event())  # must not raise

    assert pool.checkout_count == 2


def test_record_does_not_retry_invalid_password():
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_invalid_password = type(
        "InvalidPassword", (fake_operational_error,), {"__module__": "psycopg"}
    )
    broken = _FakeConn(raises=fake_invalid_password("password authentication failed"))
    pool = _FakePool([broken])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        sink.record(_event())

    assert pool.checkout_count == 1


def test_record_does_not_retry_pool_closed():
    """test-specialist review (pre-implementation, ADR-0011): see
    `PostgresLifecycleLedger`'s identical test for the full rationale."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_pool_closed = type(
        "PoolClosed", (fake_operational_error,), {"__module__": "psycopg_pool"}
    )
    broken = _FakeConn(raises=fake_pool_closed("the pool is closed"))
    pool = _FakePool([broken])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        sink.record(_event())

    assert pool.checkout_count == 1


def test_record_raises_a_clear_storage_error_when_the_schema_is_not_migrated():
    fake_undefined_table = type("UndefinedTable", (Exception,), {"__module__": "psycopg.errors"})
    broken = _FakeConn(raises=fake_undefined_table('relation "audit_events" does not exist'))
    pool = _FakePool([broken])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError, match="mrag db migrate"):
        sink.record(_event())


def test_record_computes_expires_at_from_timestamp_and_retention_days():
    """Codex review HIGH-001 (second post-implementation pass):
    `expires_at` is no longer a `GENERATED ALWAYS ... STORED` column
    (PostgreSQL rejects that — `timestamptz + interval` is STABLE, not
    IMMUTABLE) — it is computed once in Python and passed as an ordinary
    INSERT value. Confirms `record()` actually does that arithmetic and
    that it lands in the right parameter position."""
    captured_params: list = []

    def _executor(sql, params):
        captured_params.append(params)
        return _FakeCursor()

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)
    event_timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    event = _event(timestamp=event_timestamp, retention_days=30)

    sink.record(event)

    params = captured_params[0]
    assert params[-2] == 30  # retention_days
    assert params[-1] == event_timestamp + timedelta(days=30)  # expires_at


# ---------------------------------------------------------------------------
# ADR-0011: retention (purge_expired() / count_expired()).
# ---------------------------------------------------------------------------


def test_purge_expired_refuses_without_allow_purge():
    """security-specialist (pre-implementation): a fail-closed guard — the
    manifest-wired, request-serving sink instance never sets
    `allow_purge=True`, so this must raise even before touching the pool."""
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    with pytest.raises(SecurityError):
        sink.purge_expired()


def test_purge_expired_refusal_executes_zero_sql():
    pool = _FakePool([])  # any checkout would raise IndexError -- proves none happened
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(SecurityError):
        sink.purge_expired()

    assert pool.checkout_count == 0


def test_count_expired_works_without_allow_purge():
    """A dry-run/monitoring method must not carry the same gate as the
    destructive one (security-specialist: flag-inversion risk of a single
    `dry_run=` flag instead)."""
    select_conn = _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[(0,)]))
    pool = _FakePool([select_conn])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    count = sink.count_expired(now=datetime.now(UTC))

    assert count == 0


def test_purge_expired_rejects_a_timezone_naive_now():
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", allow_purge=True)

    with pytest.raises(ValueError, match="timezone-aware"):
        sink.purge_expired(now=datetime(2026, 1, 1))


def test_count_expired_rejects_a_timezone_naive_now():
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    with pytest.raises(ValueError, match="timezone-aware"):
        sink.count_expired(now=datetime(2026, 1, 1))


def test_purge_expired_is_a_single_atomic_statement_per_batch():
    """Codex review MEDIUM-002 (post-implementation): select-and-delete
    used to be two independent autocommit statements (two pool checkouts
    per batch) — two concurrent purge_expired() calls could both SELECT
    the same batch, the first DELETE would remove it, and the second
    DELETE (targeting already-deleted ids) would affect zero rows while
    its caller still counted the SELECT's row count, over-reporting what
    was actually deleted. Now one checkout issues one CTE-based
    `DELETE ... RETURNING`, so exactly one checkout happens per batch and
    the count comes only from what the DELETE itself returned."""
    delete_conn = _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[("id-1",), ("id-2",)]))
    pool = _FakePool([delete_conn, _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    deleted = sink.purge_expired(now=datetime.now(UTC))

    assert deleted == 2
    assert pool.checkout_count == 2  # one batch with rows, one empty batch that stops the loop


def test_purge_expired_never_retries_a_connection_level_failure():
    """Codex review MEDIUM-001 (second post-implementation pass): unlike
    `record()` (whose `INSERT ... ON CONFLICT DO NOTHING` is safe to
    retry), `_DELETE_EXPIRED_BATCH` must NOT be retried on a connection-
    level failure — if PostgreSQL committed the DELETE before the
    connection broke, a retry would silently pick up and delete a
    *different* batch, and the first batch's row count would never be
    added to the total (an under-count of real deletions, not merely a
    theoretical risk). Proven here the same way the ledger's equivalent
    test is: a connection-level error must propagate as a `StorageError`
    after exactly ONE checkout, never a second, retried one."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    broken = _FakeConn(raises=fake_operational_error("connection lost"))
    pool = _FakePool([broken])  # a second checkout would raise IndexError if attempted
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    with pytest.raises(StorageError):
        sink.purge_expired(now=datetime.now(UTC))

    assert pool.checkout_count == 1


def test_purge_expired_loops_past_a_short_batch_and_stops_only_on_empty(monkeypatch):
    """Codex review MEDIUM-002 (post-implementation): the loop must
    continue past a batch smaller than the page size, not just an empty
    one — `FOR UPDATE SKIP LOCKED` (see `_DELETE_EXPIRED_BATCH`) can make a
    batch short because some expired rows are currently locked by a
    concurrent purge call, not because none remain. Stopping only on
    short-batch (the pre-fix behavior) could leave those rows unprocessed
    longer than necessary."""
    from modular_rag.adapters.audit import postgres_sink as postgres_sink_module

    monkeypatch.setattr(postgres_sink_module, "_PURGE_BATCH_SIZE", 2)
    batches = [
        [("id-1",), ("id-2",)],  # full batch -- loop continues
        [("id-3",)],  # short batch -- loop must still continue
        [],  # empty batch -- loop stops here
    ]
    call_count = {"n": 0}

    def _executor(sql, params):
        rows = batches[call_count["n"]]
        call_count["n"] += 1
        return _FakeCursor(rows=rows)

    pool = _FakePool([_FakeConn(executor=_executor) for _ in range(3)])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    deleted = sink.purge_expired(now=datetime.now(UTC))

    assert deleted == 3
    assert call_count["n"] == 3  # continued past the short batch, stopped only on empty


def test_purge_expired_stops_immediately_when_nothing_is_expired():
    delete_conn = _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))
    pool = _FakePool([delete_conn])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    deleted = sink.purge_expired(now=datetime.now(UTC))

    assert deleted == 0
    assert pool.checkout_count == 1  # one empty batch, no further checkout


def test_purge_expired_query_uses_expires_at_and_skip_locked():
    """Codex review MEDIUM-003 (post-implementation, sanity check): the
    generated `expires_at` column and `FOR UPDATE SKIP LOCKED` are actually
    wired into the query this method issues — the real index-usage proof
    needs a live PostgreSQL `EXPLAIN` (tests/integration/test_postgres_audit_sink.py),
    but this at least proves the SQL text matches the fix, not just the
    surrounding Python control flow."""
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[])

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    sink.purge_expired(now=datetime.now(UTC))

    assert "expires_at" in captured_sql[0]
    assert "FOR UPDATE SKIP LOCKED" in captured_sql[0]
    assert "retention_days > 0" in captured_sql[0]


def test_count_expired_query_uses_expires_at():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[(0,)])

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresAuditSink(dsn="postgresql://unused/unused", pool=pool)

    sink.count_expired(now=datetime.now(UTC))

    assert "expires_at" in captured_sql[0]


def test_retention_days_boundary_uses_the_configured_field_validation():
    """`AuditEvent.retention_days` gained `Field(ge=1)` validation under
    ADR-0011 — a zero/negative value must be rejected at construction, not
    silently treated as "already expired" by the purge query."""
    with pytest.raises(ValueError):
        _event(retention_days=0)
    with pytest.raises(ValueError):
        _event(retention_days=-1)
    assert _event(retention_days=1).retention_days == 1
