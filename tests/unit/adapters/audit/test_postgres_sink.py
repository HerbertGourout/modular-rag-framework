"""Unit tests for adapters/audit/postgres_sink.py::PostgresAuditSink.
Service-free coverage using hand-built fake connections rather than a real
psycopg connection (same pattern as
tests/unit/adapters/vectorstores/test_qdrant_store.py's
test_close_releases_the_client_if_one_was_opened). Everything needing a real
DDL/insert round-trip (record(), append-only behavior) needs a live
PostgreSQL and is covered by tests/integration/test_postgres_audit_sink.py
instead — this file exists for close()/idempotency (Codex review, MED-002)
and, since Lot 6 (readiness and resilience), check_health()/timeout/the
connection concurrency lock.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
from modular_rag.core.resilience import CircuitBreaker


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_close_releases_the_connection_if_one_was_opened():
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")
    fake = _FakeConnection()
    sink._conn = fake  # bypass _get_connection(); no real psycopg/network needed

    sink.close()

    assert fake.closed is True
    assert sink._conn is None


def test_close_is_a_no_op_when_no_connection_was_ever_opened():
    PostgresAuditSink(dsn="postgresql://unused/unused").close()  # must not raise


def test_close_is_idempotent():
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")
    sink._conn = _FakeConnection()

    sink.close()
    sink.close()  # calling twice must not raise, second call is a no-op


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience).
# ---------------------------------------------------------------------------


def test_default_timeout_is_thirty_seconds():
    assert PostgresAuditSink(dsn="postgresql://unused/unused")._timeout == 30.0


class _FakeCursor:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeHealthyConnection:
    def execute(self, sql, *args, **kwargs):
        return _FakeCursor()


def _install_fake_psycopg_module(monkeypatch, connect):
    """Codex review HIGH-001 (Lot 6, fifth pass): see
    `PostgresLifecycleLedger`'s identical helper for the full rationale —
    `check_health()` now always does a real `import psycopg;
    psycopg.connect(...)`, stubbed here via `sys.modules` since `psycopg`
    is not installed in this dev environment."""
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)


class _FakeProbeConnection:
    """Stands in for `with psycopg.connect(...) as conn:` — check_health()'s
    only use of a connection since the HIGH-001 redesign."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def execute(self, sql, *args, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _FakeCursor()


def test_check_health_returns_healthy_on_a_successful_select_1(monkeypatch):
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


def test_check_health_bakes_in_statement_timeout_via_connect_options(monkeypatch):
    """Codex review HIGH-001 (Lot 6, fifth pass): see
    `PostgresLifecycleLedger`'s identical test for the full rationale —
    `statement_timeout` must be active from the very first query, baked
    into `options=` at connect time rather than set via a separate
    statement afterward."""
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
    `PostgresLifecycleLedger`'s identical test for the full rationale — TCP
    keepalives bound detection of a transport gone silent after the
    handshake, independent of anything the server enforces."""
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


def test_check_health_never_touches_the_cached_connection(monkeypatch):
    """See `PostgresLifecycleLedger`'s identical test for the full
    rationale (Codex review HIGH-001, Lot 6, fifth pass) — a connection
    cached from real `record()` traffic must be left completely untouched."""

    class _MustNotBeTouchedConnection:
        def execute(self, *args, **kwargs):
            raise AssertionError("check_health() must never use the cached connection")

    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    sink = PostgresAuditSink(dsn="postgresql://unused/unused")
    cached = _MustNotBeTouchedConnection()
    sink._conn = cached

    results = sink.check_health()

    assert results[0].healthy is True
    assert sink._conn is cached


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


class _TrackingConnection:
    """Records the maximum number of `execute()` calls ever in flight at
    once — proves `PostgresAuditSink`'s lock actually serializes access to
    the single shared connection. `record()` runs on `/answer`'s request
    path (`RAGEngine._audit()`), so this sink is reached exactly as
    concurrently as the API itself is."""

    def __init__(self) -> None:
        self._counter_lock = threading.Lock()
        self.concurrent = 0
        self.max_concurrent = 0

    def execute(self, *args, **kwargs):
        with self._counter_lock:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        time.sleep(0.01)  # widen the window so a missing lock would likely be caught
        with self._counter_lock:
            self.concurrent -= 1
        return _FakeCursor()


def test_concurrent_record_calls_never_execute_on_the_connection_simultaneously():
    from modular_rag.contracts.audit import AuditEvent, AuditEventType

    sink = PostgresAuditSink(dsn="postgresql://unused/unused")
    tracking = _TrackingConnection()
    sink._conn = tracking  # bypass _get_connection(); no real psycopg/network needed
    event = AuditEvent(event_type=AuditEventType.RUN_SUCCEEDED, correlation_id="c1", tenant_id="t1")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: sink.record(event), range(10)))

    assert tracking.max_concurrent == 1
