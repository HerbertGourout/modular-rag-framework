"""Integration tests for PostgresAuditSink — requires PostgreSQL on
localhost:5432 (same "assumes a running local service" convention as
test_qdrant_store.py). Not run by default — deselect with `-m "not integration"`.
"""
import os

import pytest

from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
from modular_rag.contracts.audit import AuditEvent, AuditEventType

DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture()
def sink():
    s = PostgresAuditSink(dsn=DSN)
    s._get_connection().execute("DELETE FROM audit_events WHERE tenant_id = 'test-tenant'")
    try:
        yield s
    finally:
        # `_get_connection()` transparently reopens if the test already closed the sink
        # (e.g. the close()/idempotency tests below) — close explicitly afterward either
        # way, rather than leaking whichever connection this cleanup ends up using
        # (Codex review, MED-002).
        s._get_connection().execute("DELETE FROM audit_events WHERE tenant_id = 'test-tenant'")
        s.close()


def _event(**overrides: object) -> AuditEvent:
    defaults: dict[str, object] = {
        "event_type": AuditEventType.RUN_SUCCEEDED,
        "correlation_id": "corr-1",
        "tenant_id": "test-tenant",
        "payload": {"answer_length": 42},
    }
    defaults.update(overrides)
    return AuditEvent(**defaults)  # type: ignore[arg-type]


@pytest.mark.integration
def test_record_persists_event_retrievable_via_raw_sql(sink):
    event = _event()

    sink.record(event)

    row = sink._get_connection().execute(
        "SELECT id, event_type, tenant_id, payload FROM audit_events WHERE id = %s", (event.id,)
    ).fetchone()
    assert row is not None
    assert row[0] == event.id
    assert row[1] == "run_succeeded"
    assert row[2] == "test-tenant"


@pytest.mark.integration
def test_record_is_append_only_on_conflicting_id(sink):
    event = _event()

    sink.record(event)
    sink.record(event)  # ON CONFLICT (id) DO NOTHING — must not raise, must not duplicate

    count = sink._get_connection().execute(
        "SELECT count(*) FROM audit_events WHERE id = %s", (event.id,)
    ).fetchone()[0]
    assert count == 1


@pytest.mark.integration
def test_name_reports_postgres(sink):
    assert sink.name() == "postgres"


@pytest.mark.integration
def test_close_releases_the_connection_and_is_idempotent(sink):
    sink.record(_event())  # force a real connection to actually exist first
    assert sink._conn is not None

    sink.close()
    assert sink._conn is None

    sink.close()  # must not raise on an already-closed / never-opened sink


@pytest.mark.integration
def test_close_on_a_sink_that_never_connected_is_a_safe_no_op():
    unused_sink = PostgresAuditSink(dsn=DSN)
    unused_sink.close()  # no _get_connection() call ever made — must not raise
