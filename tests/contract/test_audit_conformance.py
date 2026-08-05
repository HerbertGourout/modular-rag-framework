"""Semantic conformance tests for the AuditSink port (contracts/audit.py).

Parametrized over `InMemoryAuditSink` only. `PostgresAuditSink`
(adapters/audit/postgres_sink.py) is excluded here for the same reason
`.claude/rules/tests.md` excludes `VectorRetriever`/`HybridRetriever` from
this suite: it requires a real external service. It is instead covered by
`tests/integration/test_postgres_audit_sink.py` (`@pytest.mark.integration`).
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.audit import AuditEvent, AuditEventType, AuditSink
from modular_rag.security.audit.store import InMemoryAuditSink

SINK_FACTORIES = [InMemoryAuditSink]


def _event(**overrides: object) -> AuditEvent:
    defaults: dict[str, object] = {
        "event_type": AuditEventType.RUN_SUCCEEDED,
        "correlation_id": "corr-1",
        "tenant_id": "tenant-a",
    }
    defaults.update(overrides)
    return AuditEvent(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_sink_satisfies_the_protocol(sink_factory: type) -> None:
    assert isinstance(sink_factory(), AuditSink)


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_record_is_append_only_and_idempotent_on_id(sink_factory: type) -> None:
    sink = sink_factory()
    event = _event()

    sink.record(event)
    sink.record(event)  # same id, recorded again — protocol doesn't require dedup at write time

    assert len(sink.events) == 2  # type: ignore[attr-defined]
    assert all(e.id == event.id for e in sink.events)  # type: ignore[attr-defined]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
async def test_arecord_persists_the_same_way_as_record(sink_factory: type) -> None:
    sink = sink_factory()
    event = _event(event_type=AuditEventType.RUN_FAILED)

    await sink.arecord(event)

    assert len(sink.events) == 1  # type: ignore[attr-defined]
    assert sink.events[0].event_type == AuditEventType.RUN_FAILED  # type: ignore[attr-defined]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_sink_has_a_name(sink_factory: type) -> None:
    assert sink_factory().name()
