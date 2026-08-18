"""Integration tests for PostgresLifecycleLedger — requires PostgreSQL on
localhost:5432 (same "assumes a running local service" convention as
test_qdrant_store.py / test_postgres_audit_sink.py, Lot 10). Not run by
default — deselect with `-m "not integration"`.
"""
import os

import pytest

from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger
from modular_rag.contracts.lifecycle import DocumentStatus

DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture()
def ledger():
    ledger = PostgresLifecycleLedger(dsn=DSN)
    ledger._get_connection().execute(
        "DELETE FROM document_lifecycle WHERE document_key = 'test-key-1'"
    )
    try:
        yield ledger
    finally:
        # `_get_connection()` transparently reopens if the test already closed the ledger
        # (e.g. the close()/idempotency tests below) — close explicitly afterward either
        # way, rather than leaking whichever connection this cleanup ends up using
        # (Codex review, MED-002).
        ledger._get_connection().execute(
            "DELETE FROM document_lifecycle WHERE document_key = 'test-key-1'"
        )
        ledger.close()


@pytest.mark.integration
def test_record_ingested_then_get_round_trips(ledger):
    written = ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1", "c2"])

    read = ledger.get("test-key-1")

    assert read is not None
    assert read.document_key == "test-key-1"
    assert read.content_hash == "hash-a"
    assert read.chunk_ids == ["c1", "c2"]
    assert read.version == written.version


@pytest.mark.integration
def test_record_ingested_again_bumps_version(ledger):
    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])

    second = ledger.record_ingested("test-key-1", "tenant-a", "hash-b", ["c2", "c3"])

    assert second.version == 2
    read = ledger.get("test-key-1")
    assert read.chunk_ids == ["c2", "c3"]


@pytest.mark.integration
def test_tombstone_persists_status_and_clears_chunk_ids(ledger):
    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])

    ledger.tombstone("test-key-1")

    read = ledger.get("test-key-1")
    assert read.status == DocumentStatus.TOMBSTONED
    assert read.chunk_ids == []


@pytest.mark.integration
def test_name_reports_postgres(ledger):
    assert ledger.name() == "postgres"


@pytest.mark.integration
def test_list_active_excludes_tombstoned_records(ledger):
    """Lot 12b, docs/refactoring-plan.md."""
    ledger._get_connection().execute(
        "DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'"
    )
    try:
        ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
        ledger.record_ingested("test-key-2", "tenant-a", "hash-b", ["c2"])
        ledger.tombstone("test-key-2")

        active_keys = {r.document_key for r in ledger.list_active()}

        assert "test-key-1" in active_keys
        assert "test-key-2" not in active_keys
    finally:
        ledger._get_connection().execute(
            "DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'"
        )


@pytest.mark.integration
def test_export_all_includes_tombstoned_records(ledger):
    """Lot 12c, docs/refactoring-plan.md."""
    ledger._get_connection().execute(
        "DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'"
    )
    try:
        ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
        ledger.record_ingested("test-key-2", "tenant-a", "hash-b", ["c2"])
        ledger.tombstone("test-key-2")

        keys = {r.document_key for r in ledger.export_all()}

        assert {"test-key-1", "test-key-2"} <= keys
    finally:
        ledger._get_connection().execute(
            "DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'"
        )


@pytest.mark.integration
def test_restore_record_writes_verbatim(ledger):
    original = ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])

    ledger.restore_record(original)

    read = ledger.get("test-key-1")
    assert read.version == original.version
    assert read.created_at == original.created_at


@pytest.mark.integration
def test_close_releases_the_connection_and_is_idempotent(ledger):
    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])  # forces a real connection
    assert ledger._conn is not None

    ledger.close()
    assert ledger._conn is None

    ledger.close()  # must not raise on an already-closed / never-opened ledger


@pytest.mark.integration
def test_close_on_a_ledger_that_never_connected_is_a_safe_no_op():
    unused_ledger = PostgresLifecycleLedger(dsn=DSN)
    unused_ledger.close()  # no _get_connection() call ever made — must not raise


@pytest.mark.integration
def test_check_health_reports_healthy_against_a_real_postgres(ledger):
    """Lot 6 (readiness and resilience)."""
    results = ledger.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


@pytest.mark.integration
def test_check_health_reports_unhealthy_against_an_unreachable_postgres():
    unreachable = PostgresLifecycleLedger(
        dsn="postgresql://postgres:postgres@localhost:1/postgres", timeout=1.0
    )

    results = unreachable.check_health()

    assert results[0].healthy is False
    assert results[0].detail is not None
