"""Unit tests for security/feedback/store.py — InMemoryFeedbackSink. Batch 14,
ADR-0014.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from modular_rag.contracts.feedback import Feedback
from modular_rag.security.feedback.store import InMemoryFeedbackSink


def _feedback(idempotency_key: str = "k1", **overrides: object) -> Feedback:
    defaults: dict[str, object] = {"trace_id": "t1", "idempotency_key": idempotency_key}
    defaults.update(overrides)
    return Feedback(**defaults)  # type: ignore[arg-type]


def test_record_appends_a_new_idempotency_key() -> None:
    sink = InMemoryFeedbackSink()

    sink.record(_feedback("k1"))
    sink.record(_feedback("k2"))

    assert len(sink.records) == 2


def test_record_is_a_no_op_for_a_repeated_idempotency_key() -> None:
    sink = InMemoryFeedbackSink()

    sink.record(_feedback("k1", rating=None))
    sink.record(_feedback("k1", correction_text="a different payload, same key"))

    assert len(sink.records) == 1
    # First write wins — a retried submission never overwrites the original.
    assert sink.records[0].correction_text is None


def test_records_property_returns_a_copy() -> None:
    sink = InMemoryFeedbackSink()
    sink.record(_feedback("k1"))

    snapshot = sink.records
    snapshot.append(_feedback("k2"))

    assert len(sink.records) == 1


def test_list_since_returns_everything_when_since_is_none() -> None:
    sink = InMemoryFeedbackSink()
    sink.record(_feedback("k1"))
    sink.record(_feedback("k2"))

    assert len(sink.list_since()) == 2


def test_list_since_filters_by_created_at() -> None:
    sink = InMemoryFeedbackSink()
    now = datetime.now(UTC)
    sink.record(_feedback("old", created_at=now - timedelta(days=10)))
    sink.record(_feedback("recent", created_at=now))

    recent_only = sink.list_since(now - timedelta(days=1))

    assert len(recent_only) == 1
    assert recent_only[0].idempotency_key == "recent"


def test_get_returns_the_stored_record_for_a_matching_key() -> None:
    sink = InMemoryFeedbackSink()
    stored = _feedback("k1", tenant_id="tenant-a")
    sink.record(stored)

    assert sink.get("tenant-a", "k1") is stored


def test_get_returns_none_for_an_unknown_key() -> None:
    sink = InMemoryFeedbackSink()

    assert sink.get(None, "does-not-exist") is None


def test_get_is_scoped_per_tenant() -> None:
    sink = InMemoryFeedbackSink()
    sink.record(_feedback("k1", tenant_id="tenant-a"))

    assert sink.get("tenant-b", "k1") is None
