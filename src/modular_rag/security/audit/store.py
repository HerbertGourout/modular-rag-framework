"""In-memory AuditSink reference implementation (Lot 10, docs/refactoring-plan.md
§09 V1.2 "Immutable append-only event store"). A real, working sink — not a
mock — for tests and local/dev use before a durable backend
(`adapters.audit.postgres_sink.PostgresAuditSink`) is configured.
"""
from __future__ import annotations

from modular_rag.contracts.audit import AuditEvent


class InMemoryAuditSink:
    """Append-only: events are only ever appended, never mutated or removed,
    matching the `AuditSink` Protocol's intentionally missing update/delete
    methods."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    async def arecord(self, event: AuditEvent) -> None:
        self.record(event)

    def name(self) -> str:
        return "in-memory"

    @property
    def events(self) -> list[AuditEvent]:
        """Read-only snapshot for tests/inspection — returns a copy so callers
        can't mutate the append-only log through the accessor."""
        return list(self._events)

    def events_for_correlation(self, correlation_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.correlation_id == correlation_id]
