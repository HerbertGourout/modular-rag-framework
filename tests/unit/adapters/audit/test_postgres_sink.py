"""Unit tests for adapters/audit/postgres_sink.py::PostgresAuditSink.close() —
service-free coverage for the idempotent close() contract, using a hand-built
fake connection rather than a real psycopg connection (same pattern as
tests/unit/adapters/vectorstores/test_qdrant_store.py's
test_close_releases_the_client_if_one_was_opened). Everything else about this
sink (record(), the DDL, append-only behavior) needs a live PostgreSQL and is
covered by tests/integration/test_postgres_audit_sink.py instead — this file
exists specifically because close()/idempotency previously had zero coverage
in the standard, service-free unit+contract gate (Codex review, MED-002).
"""
from __future__ import annotations

from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink


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
