"""Unit tests for security/audit/store.py — InMemoryAuditSink. Lot 10,
docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.audit import AuditEvent, AuditEventType
from modular_rag.security.audit.store import InMemoryAuditSink


def _event(correlation_id: str = "corr-1") -> AuditEvent:
    return AuditEvent(
        event_type=AuditEventType.RUN_SUCCEEDED,
        correlation_id=correlation_id,
        tenant_id="tenant-a",
    )


def test_record_appends_event() -> None:
    sink = InMemoryAuditSink()

    sink.record(_event())

    assert len(sink.events) == 1


def test_events_property_returns_a_copy_not_the_live_list() -> None:
    sink = InMemoryAuditSink()
    sink.record(_event())

    snapshot = sink.events
    snapshot.append(_event())

    assert len(sink.events) == 1  # mutating the snapshot must not affect the sink


def test_events_for_correlation_filters_by_correlation_id() -> None:
    sink = InMemoryAuditSink()
    sink.record(_event(correlation_id="corr-1"))
    sink.record(_event(correlation_id="corr-2"))
    sink.record(_event(correlation_id="corr-1"))

    matched = sink.events_for_correlation("corr-1")

    assert len(matched) == 2
    assert all(e.correlation_id == "corr-1" for e in matched)
