"""Unit tests for adapters/lifecycle/postgres_ledger.py::PostgresLifecycleLedger.
Service-free coverage using hand-built fake connections rather than a real
psycopg connection (same pattern as
tests/unit/adapters/vectorstores/test_qdrant_store.py's
test_close_releases_the_client_if_one_was_opened). Everything needing a real
DDL/query round-trip (record_ingested(), tombstone()) needs a live
PostgreSQL and is covered by tests/integration/test_postgres_lifecycle_ledger.py
instead — this file exists for close()/idempotency (Codex review, MED-002)
and, since Lot 6 (readiness and resilience), check_health()/timeout/the
connection concurrency lock.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger
from modular_rag.core.errors import StorageError
from modular_rag.core.resilience import CircuitBreaker


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_close_releases_the_connection_if_one_was_opened():
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    fake = _FakeConnection()
    ledger._conn = fake  # bypass _get_connection(); no real psycopg/network needed

    ledger.close()

    assert fake.closed is True
    assert ledger._conn is None


def test_close_is_a_no_op_when_no_connection_was_ever_opened():
    PostgresLifecycleLedger(dsn="postgresql://unused/unused").close()  # must not raise


def test_close_is_idempotent():
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    ledger._conn = _FakeConnection()

    ledger.close()
    ledger.close()  # calling twice must not raise, second call is a no-op


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience).
# ---------------------------------------------------------------------------


def test_default_timeout_is_thirty_seconds():
    assert PostgresLifecycleLedger(dsn="postgresql://unused/unused")._timeout == 30.0


class _FakeCursor:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeHealthyConnection:
    def execute(self, sql, *args, **kwargs):
        return _FakeCursor()


def _install_fake_psycopg_module(monkeypatch, connect):
    """Codex review HIGH-001 (Lot 6, fifth pass): `check_health()` now
    always does a real `import psycopg; psycopg.connect(...)` — there is no
    more branch reachable via a hand-built fake sitting on `self._conn`.
    `psycopg` is not installed in this dev environment (see this module's
    own docstring), so `import psycopg` is stubbed via `sys.modules`
    instead: Python's import system checks `sys.modules` first, before ever
    touching the real package."""
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
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")

    results = ledger.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


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


def test_check_health_never_touches_the_cached_connection(monkeypatch):
    """The prior design reused/mutated the shared `self._conn` on its warm
    path (Codex review HIGH-001, Lot 6, fifth pass) — the redesign always
    opens its own dedicated connection, so a connection cached from real
    traffic must be left completely untouched, healthy or not."""

    class _MustNotBeTouchedConnection:
        def execute(self, *args, **kwargs):
            raise AssertionError("check_health() must never use the cached connection")

    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    cached = _MustNotBeTouchedConnection()
    ledger._conn = cached

    results = ledger.check_health()

    assert results[0].healthy is True
    assert ledger._conn is cached  # untouched, not invalidated either


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


def test_get_retries_and_reconnects_after_a_connection_level_failure_on_a_warm_connection(
    monkeypatch,
):
    """Codex review HIGH-003 (Lot 6): `_execute()` retries a query that
    fails with a connection-level error, invalidating the broken connection
    and reconnecting rather than repeating the same failure against a dead
    socket — previously the retry+circuit wrapping covered only the very
    first connect. `psycopg` is not installed in this dev environment, so
    the fake exception below carries `psycopg.OperationalError`'s real
    module/class *name* — `_is_connection_level_error()` classifies by
    name specifically so this works without the real package (see its own
    docstring)."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})

    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    broken_calls = {"n": 0}

    class _BrokenConnection:
        def execute(self, *args, **kwargs):
            broken_calls["n"] += 1
            raise fake_operational_error("connection lost")

    ledger._conn = _BrokenConnection()
    reconnect_calls = {"n": 0}

    def _fake_connect_once() -> None:
        reconnect_calls["n"] += 1
        ledger._conn = _FakeHealthyConnection()

    monkeypatch.setattr(ledger, "_connect_once", _fake_connect_once)

    row = ledger.get("doc-1")

    assert row is None  # _FakeHealthyConnection's cursor.fetchone() returns None
    assert broken_calls["n"] == 1  # the broken connection was tried exactly once
    assert reconnect_calls["n"] == 1  # then reconnected exactly once, not retried again


def test_get_retries_a_psycopg_operational_error_subclass_like_adminshutdown(monkeypatch):
    """Codex review MED-001 (Lot 6, second pass): psycopg raises specific
    subclasses of `OperationalError` for specific SQLSTATE conditions
    (`AdminShutdown`, `ConnectionFailure`, ...) rather than the generic
    base on a server-initiated disconnect (psycopg >=3.2.4) — an
    exact-name match against only "OperationalError" missed these
    entirely, treating a recoverable server restart as a permanent
    failure. The fake exception below has `psycopg.OperationalError` as
    its real base class (by MRO), named `AdminShutdown` — matching what
    psycopg actually raises."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_admin_shutdown = type(
        "AdminShutdown", (fake_operational_error,), {"__module__": "psycopg"}
    )

    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    broken_calls = {"n": 0}

    class _BrokenConnection:
        def execute(self, *args, **kwargs):
            broken_calls["n"] += 1
            raise fake_admin_shutdown("server shutting down")

    ledger._conn = _BrokenConnection()
    reconnect_calls = {"n": 0}

    def _fake_connect_once() -> None:
        reconnect_calls["n"] += 1
        ledger._conn = _FakeHealthyConnection()

    monkeypatch.setattr(ledger, "_connect_once", _fake_connect_once)

    row = ledger.get("doc-1")

    assert row is None
    assert broken_calls["n"] == 1
    assert reconnect_calls["n"] == 1


def test_get_does_not_retry_invalid_password():
    """`InvalidPassword` also subclasses `OperationalError` by MRO, but
    retrying a bad password wastes the retry budget on an error retrying
    cannot fix — explicitly excluded (Codex review MED-001), same
    reasoning `ConfigurationError` is excluded from Qdrant's retryable
    set."""
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_invalid_password = type(
        "InvalidPassword", (fake_operational_error,), {"__module__": "psycopg"}
    )

    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    calls = {"n": 0}

    class _BadPasswordConnection:
        def execute(self, *args, **kwargs):
            calls["n"] += 1
            raise fake_invalid_password("password authentication failed")

    ledger._conn = _BadPasswordConnection()

    with pytest.raises(StorageError):
        ledger.get("doc-1")

    assert calls["n"] == 1  # not retried
    assert ledger._conn is not None  # not invalidated either -- not a connection-level failure


class _TrackingConnection:
    """Records the maximum number of `execute()` calls ever in flight at
    once — proves `PostgresLifecycleLedger`'s lock actually serializes
    access to the single shared connection, not just that it exists."""

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


def test_concurrent_get_calls_never_execute_on_the_connection_simultaneously():
    """architecture-reviewer/observability-expert-style finding (Lot 6): a
    raw psycopg Connection is not safe for concurrent execute() calls from
    multiple threads — FastAPI's sync routes run concurrently across
    threadpool workers. `get()`'s `with self._lock:` must serialize every
    call onto the shared connection."""
    ledger = PostgresLifecycleLedger(dsn="postgresql://unused/unused")
    tracking = _TrackingConnection()
    ledger._conn = tracking  # bypass _get_connection(); no real psycopg/network needed

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: ledger.get("doc-1"), range(10)))

    assert tracking.max_concurrent == 1
