"""Unit tests for adapters/review/postgres_queue.py::PostgresReviewQueue.
Batch 14, ADR-0014. Same fake-pool pattern as
tests/unit/adapters/feedback/test_postgres_sink.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue
from modular_rag.contracts.review import ReviewItem
from modular_rag.core.errors import ConfigurationError, ModularRAGError, SecurityError, StorageError
from modular_rag.core.models.answer import Answer


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


def _item(**overrides: object) -> ReviewItem:
    defaults: dict[str, object] = {
        "answer_id": "a1", "query_id": "q1", "reason": "low confidence",
    }
    defaults.update(overrides)
    return ReviewItem(**defaults)  # type: ignore[arg-type]


def test_invalid_pool_sizing_is_rejected_at_construction():
    with pytest.raises(ConfigurationError):
        PostgresReviewQueue(dsn="postgresql://unused/unused", min_size=5, max_size=3)


def test_should_review_is_a_pure_threshold_check_no_db_access():
    """No pool given at all -- constructing one would raise on first real
    use, proving should_review() never touches the database."""
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", threshold=0.5)

    assert queue.should_review(Answer(query_id="q", text="x", confidence=0.1)) is True
    assert queue.should_review(Answer(query_id="q", text="x", confidence=0.9)) is False


def test_enqueue_computes_expires_at_from_created_at_and_retention_days():
    captured_params: list = []

    def _executor(sql, params):
        captured_params.append(params)
        return _FakeCursor()

    pool = _FakePool([_FakeConn(executor=_executor)])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    item = _item(created_at=created_at, retention_days=30)

    queue.enqueue(item)

    params = captured_params[0]
    assert params[-1] == created_at + timedelta(days=30)  # expires_at


def test_resolve_returns_id_and_succeeds_when_the_item_exists():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[("item-1",)]))])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    queue.resolve("item-1", approved=True, reviewer="alice")  # must not raise


def test_resolve_raises_modular_rag_error_when_the_item_does_not_exist():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[]))])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(ModularRAGError, match="No pending review item"):
        queue.resolve("unknown-id", approved=True, reviewer="alice")


def test_resolve_uses_an_atomic_update_returning_not_a_read_then_write():
    captured_sql: list[str] = []

    def _executor(sql, params):
        captured_sql.append(sql)
        return _FakeCursor(rows=[("item-1",)])

    pool = _FakePool([_FakeConn(executor=_executor)])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    queue.resolve("item-1", approved=False, reviewer="bob")

    assert "UPDATE review_items" in captured_sql[0]
    assert "RETURNING id" in captured_sql[0]
    # Codex review pass 1, HIGH-002: the compare-and-set guard that makes
    # resolution terminal — without it, a second resolve() call on an
    # already-resolved row would silently overwrite the first decision.
    assert "AND resolved = FALSE" in captured_sql[0]
    assert pool.checkout_count == 1  # one statement, not a read then a write


def test_resolve_rejects_a_second_resolution_of_the_same_item():
    """Codex review pass 1, HIGH-002: two sequential `resolve()` calls
    against the same id — the first succeeds (the row is still pending, so
    `AND resolved = FALSE` matches); the second must be rejected, not
    silently overwrite the first decision's `approved`/`reviewer`. The fake
    pool's second connection returns zero rows, exactly what the real
    `AND resolved = FALSE` guard produces against an already-resolved row."""
    pool = _FakePool(
        [
            _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[("item-1",)])),
            _FakeConn(executor=lambda sql, params: _FakeCursor(rows=[])),
        ]
    )
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    queue.resolve("item-1", approved=True, reviewer="alice")  # first: succeeds

    with pytest.raises(ModularRAGError, match="No pending review item"):
        queue.resolve("item-1", approved=False, reviewer="bob")  # second: rejected


def test_pending_reconstructs_review_items():
    row = (
        "id-1", "a1", "q1", None, "low confidence", 0.3, datetime.now(UTC),
        False, None, None, 365,
    )
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[row]))])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    pending = queue.pending

    assert len(pending) == 1
    assert pending[0].id == "id-1"
    assert pending[0].resolved is False


def test_purge_expired_refuses_without_allow_purge():
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused")

    with pytest.raises(SecurityError):
        queue.purge_expired()


def test_count_resolved_works_without_allow_purge():
    pool = _FakePool([_FakeConn(executor=lambda sql, params: _FakeCursor(rows=[(5,)]))])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    assert queue.count_resolved() == 5


def test_close_releases_the_pool():
    pool = _FakePool([])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    queue.close()

    assert pool.closed is True


def test_record_raises_storage_error_on_schema_not_migrated():
    fake_undefined_table = type("UndefinedTable", (Exception,), {"__module__": "psycopg.errors"})
    broken = _FakeConn(raises=fake_undefined_table('relation "review_items" does not exist'))
    pool = _FakePool([broken])
    queue = PostgresReviewQueue(dsn="postgresql://unused/unused", pool=pool)

    with pytest.raises(StorageError, match="mrag db migrate"):
        queue.enqueue(_item())
