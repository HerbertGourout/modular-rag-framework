"""Unit tests for adapters/feedback/postgres_sink.py::PostgresFeedbackSink.
Batch 14, ADR-0014. Service-free coverage using hand-built fakes, same
pattern as tests/unit/adapters/audit/test_postgres_sink.py — see that file's
own docstring for the full rationale (pool-per-attempt checkout, retry
classification, `pool=` injection so psycopg need not be installed).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modular_rag.adapters.feedback.postgres_sink import PostgresFeedbackSink
from modular_rag.contracts.feedback import Feedback, FeedbackRating
from modular_rag.core.errors import ConfigurationError, SecurityError, StorageError


def _install_fake_psycopg_module(monkeypatch, connect):
    import sys
    import types

    fake_module = types.ModuleType("psycopg")
    fake_module.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeConn:
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
            raise AssertionError("execute() called outside its `with` block")
        if self._raises is not None:
            raise self._raises
        if self._executor is not None:
            return self._executor(sql, params)
        return _FakeCursor()


class _FakePool:
    def __init__(self, connections: list[_FakeConn]) -> None:
        self._connections = list(connections)
        self.checkout_count = 0
        self.closed = False

    def connection(self, timeout=None):
        self.checkout_count += 1
        return self._connections.pop(0)

    def close(self) -> None:
        self.closed = True


class _FakeProbeConnection:
    def __init__(self, *, raises: Exception | None = None, schema_exists: bool = True) -> None:
        self._raises = raises
        self._schema_exists = schema_exists

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, *args, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _FakeCursor(rows=[(self._schema_exists,)])


def _feedback(**overrides: object) -> Feedback:
    defaults: dict[str, object] = {"trace_id": "t1", "idempotency_key": "k1"}
    defaults.update(overrides)
    return Feedback(**defaults)  # type: ignore[arg-type]


def test_invalid_pool_sizing_is_rejected_at_construction():
    with pytest.raises(ConfigurationError):
        PostgresFeedbackSink(dsn="postgresql://unused/unused", min_size=5, max_size=3)


def test_close_releases_the_pool():
    pool = _FakePool([])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.close()

    assert pool.closed is True
    assert sink._pool is None


def test_record_computes_expires_at_from_created_at_and_retention_days():
    captured_params: list = []

    def _executor(sql, params):
        captured_params.append(params)
        return _FakeCursor()

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    feedback = _feedback(created_at=created_at, retention_days=30)

    sink.record(feedback)

    params = captured_params[0]
    assert params[-2] == created_at + timedelta(days=30)  # expires_at
    assert params[-1] == created_at  # created_at


def test_record_uses_on_conflict_do_nothing_for_idempotency():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor()

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.record(_feedback())

    # Scoped per tenant, not a bare idempotency_key alone (Batch 14 pass 1
    # security review finding: a global-uniqueness constraint would let one
    # tenant pre-claim another tenant's key). Whitespace-normalized since
    # the real query is a multi-line triple-quoted string.
    normalized_sql = " ".join(captured_sql[0].split())
    assert "ON CONFLICT (COALESCE(tenant_id, ''), idempotency_key) DO NOTHING" in normalized_sql
    assert "ON CONFLICT (idempotency_key) DO NOTHING" not in normalized_sql


def test_record_serializes_rating_enum_to_its_string_value():
    captured_params: list = []

    def _executor(sql, params):
        captured_params.append(params)
        return _FakeCursor()

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.record(_feedback(rating=FeedbackRating.THUMBS_DOWN))

    assert captured_params[0][4] == "thumbs_down"


def test_record_does_not_retry_invalid_password():
    fake_operational_error = type("OperationalError", (Exception,), {"__module__": "psycopg"})
    fake_invalid_password = type(
        "InvalidPassword", (fake_operational_error,), {"__module__": "psycopg"}
    )
    broken = _FakeConn(raises=fake_invalid_password("bad password"))
    pool = _FakePool([broken])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError):
        sink.record(_feedback())

    assert pool.checkout_count == 1


def test_record_raises_a_clear_storage_error_when_schema_is_not_migrated():
    fake_undefined_table = type("UndefinedTable", (Exception,), {"__module__": "psycopg.errors"})
    broken = _FakeConn(raises=fake_undefined_table('relation "feedback" does not exist'))
    pool = _FakePool([broken])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError, match="mrag db migrate"):
        sink.record(_feedback())


def test_list_since_none_uses_select_all():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[])

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.list_since()

    assert "WHERE created_at" not in captured_sql[0]


def test_list_since_a_timestamp_filters_by_created_at():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[])

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.list_since(datetime.now(UTC))

    assert "WHERE created_at >= %s" in captured_sql[0]


def test_list_since_reconstructs_feedback_objects_including_rating_enum():
    row = (
        "id-1", "1.0", "t1", None, "thumbs_up", None, None, "k1", None, False, 365,
        datetime.now(UTC),
    )
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[row]))])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    results = sink.list_since()

    assert len(results) == 1
    assert results[0].rating == FeedbackRating.THUMBS_UP
    assert results[0].idempotency_key == "k1"


# ---------------------------------------------------------------------------
# get() — concrete-only idempotent-retry lookup (Codex review pass 1,
# MEDIUM-001).
# ---------------------------------------------------------------------------


def test_get_queries_by_coalesced_tenant_and_idempotency_key():
    captured: list[tuple] = []

    def _executor(sql, params):
        captured.append((sql, params))
        return _FakeCursor(rows=[])

    pool = _FakePool([_FakeConn(executor=_executor)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    sink.get("tenant-a", "k1")

    sql, params = captured[0]
    assert "COALESCE(tenant_id, '') = COALESCE(%s, '')" in sql
    assert "idempotency_key = %s" in sql
    assert params == ("tenant-a", "k1")


def test_get_returns_none_when_no_row_matches():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    assert sink.get(None, "does-not-exist") is None


def test_get_reconstructs_the_matching_feedback_row():
    row = (
        "id-1", "1.0", "t1", "tenant-a", "thumbs_down", None, None, "k1", None, False, 365,
        datetime.now(UTC),
    )
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[row]))])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    result = sink.get("tenant-a", "k1")

    assert result is not None
    assert result.id == "id-1"
    assert result.rating == FeedbackRating.THUMBS_DOWN


# ---------------------------------------------------------------------------
# Retention (mirrors PostgresAuditSink's own coverage of the shared pattern).
# ---------------------------------------------------------------------------


def test_purge_expired_refuses_without_allow_purge():
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused")

    with pytest.raises(SecurityError):
        sink.purge_expired()


def test_purge_expired_refusal_executes_zero_sql():
    pool = _FakePool([])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(SecurityError):
        sink.purge_expired()

    assert pool.checkout_count == 0


def test_count_expired_works_without_allow_purge():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[(0,)]))])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool)

    assert sink.count_expired(now=datetime.now(UTC)) == 0


def test_purge_expired_rejects_a_timezone_naive_now():
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", allow_purge=True)

    with pytest.raises(ValueError, match="timezone-aware"):
        sink.purge_expired(now=datetime(2026, 1, 1))


def test_purge_expired_stops_on_the_first_empty_batch():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    deleted = sink.purge_expired(now=datetime.now(UTC))

    assert deleted == 0
    assert pool.checkout_count == 1


def test_purge_expired_sums_across_multiple_batches():
    batches = [[("a",), ("b",)], []]
    call_count = {"n": 0}

    def _executor(sql, params):
        rows = batches[call_count["n"]]
        call_count["n"] += 1
        return _FakeCursor(rows=rows)

    pool = _FakePool([_FakeConn(executor=_executor) for _ in range(2)])
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused", pool=pool, allow_purge=True)

    deleted = sink.purge_expired(now=datetime.now(UTC))

    assert deleted == 2


# ---------------------------------------------------------------------------
# check_health() — .claude/rules/health-checks.md invariants.
# ---------------------------------------------------------------------------


def test_check_health_returns_healthy(monkeypatch):
    _install_fake_psycopg_module(monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection())
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is True
    assert results[0].name == "postgres"


def test_check_health_reports_unhealthy_when_schema_not_migrated(monkeypatch):
    _install_fake_psycopg_module(
        monkeypatch, lambda dsn, **kwargs: _FakeProbeConnection(schema_exists=False)
    )
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is False
    assert "migrat" in results[0].detail.lower()


def test_check_health_never_leaks_the_raw_exception(monkeypatch):
    def fake_connect(dsn, **kwargs):
        raise RuntimeError("connection refused to some-internal-host:5432")

    _install_fake_psycopg_module(monkeypatch, fake_connect)
    sink = PostgresFeedbackSink(dsn="postgresql://unused/unused")

    results = sink.check_health()

    assert results[0].healthy is False
    assert "some-internal-host" not in results[0].detail
