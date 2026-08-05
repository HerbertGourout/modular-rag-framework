"""Tests for contracts/audit.py — AuditEvent schema, PII/secret payload
allowlist, and AuditSink conformance. Lot 10, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from modular_rag.contracts.audit import (
    AUDIT_SCHEMA_VERSION,
    AuditEvent,
    AuditEventType,
    AuditSink,
)


def test_audit_event_defaults_schema_version_and_id() -> None:
    event = AuditEvent(
        event_type=AuditEventType.RUN_SUCCEEDED,
        correlation_id="trace-1",
        tenant_id="tenant-a",
    )
    assert event.schema_version == AUDIT_SCHEMA_VERSION
    assert event.id
    assert event.causation_id is None
    assert event.payload == {}
    assert event.retention_days == 365


def test_audit_event_accepts_allowlisted_payload_keys() -> None:
    event = AuditEvent(
        event_type=AuditEventType.RUN_FAILED,
        correlation_id="trace-1",
        tenant_id="tenant-a",
        payload={"error_type": "SecurityError", "guard_reason": "blocked"},
    )
    assert event.payload["error_type"] == "SecurityError"


def test_audit_event_rejects_non_allowlisted_payload_keys() -> None:
    """The allowlist is the enforcement mechanism against PII/secret leakage
    into audit storage — an unlisted key (e.g. a raw query or an API key)
    must fail validation, not pass through silently."""
    with pytest.raises(ValidationError, match="raw_query_text"):
        AuditEvent(
            event_type=AuditEventType.QUERY_RECEIVED,
            correlation_id="trace-1",
            tenant_id="tenant-a",
            payload={"raw_query_text": "what is my SSN 123-45-6789"},
        )


def test_audit_event_requires_correlation_and_tenant_id() -> None:
    with pytest.raises(ValidationError):
        AuditEvent(event_type=AuditEventType.RUN_SUCCEEDED)  # type: ignore[call-arg]


class _FakeAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def arecord(self, event: AuditEvent) -> None:
        self.record(event)

    def name(self) -> str:
        return "fake"


def test_fake_audit_sink_satisfies_the_protocol() -> None:
    assert isinstance(_FakeAuditSink(), AuditSink)
