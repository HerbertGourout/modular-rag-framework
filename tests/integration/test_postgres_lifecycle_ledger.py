"""Integration tests for PostgresLifecycleLedger — requires PostgreSQL on
localhost:5432 (same "assumes a running local service" convention as
test_qdrant_store.py / test_postgres_audit_sink.py, Lot 10). Not run by
default — deselect with `-m "not integration"`.

ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention):
`auto_migrate=True` replaces the retired implicit-DDL-on-connect behavior.
`_get_connection()` (referenced by this file before this change) never
existed on the real class; the real accessor is `_get_pool()`, returning a
`psycopg_pool.ConnectionPool`.
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
    ledger = PostgresLifecycleLedger(dsn=DSN, auto_migrate=True)
    with ledger._get_pool().connection() as conn:
        conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-1'")
    try:
        yield ledger
    finally:
        # `_get_pool()` transparently reconstructs the pool if the test already
        # closed the ledger (e.g. the close()/idempotency tests below) — close
        # explicitly afterward either way, rather than leaking whichever pool
        # this cleanup ends up using (Codex review, MED-002).
        with ledger._get_pool().connection() as conn:
            conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-1'")
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
    with ledger._get_pool().connection() as conn:
        conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'")
    try:
        ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
        ledger.record_ingested("test-key-2", "tenant-a", "hash-b", ["c2"])
        ledger.tombstone("test-key-2")

        active_keys = {r.document_key for r in ledger.list_active()}

        assert "test-key-1" in active_keys
        assert "test-key-2" not in active_keys
    finally:
        with ledger._get_pool().connection() as conn:
            conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'")


@pytest.mark.integration
def test_export_all_includes_tombstoned_records(ledger):
    """Lot 12c, docs/refactoring-plan.md."""
    with ledger._get_pool().connection() as conn:
        conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'")
    try:
        ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
        ledger.record_ingested("test-key-2", "tenant-a", "hash-b", ["c2"])
        ledger.tombstone("test-key-2")

        keys = {r.document_key for r in ledger.export_all()}

        assert {"test-key-1", "test-key-2"} <= keys
    finally:
        with ledger._get_pool().connection() as conn:
            conn.execute("DELETE FROM document_lifecycle WHERE document_key = 'test-key-2'")


@pytest.mark.integration
def test_restore_record_writes_verbatim(ledger):
    original = ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])

    ledger.restore_record(original)

    read = ledger.get("test-key-1")
    assert read.version == original.version
    assert read.created_at == original.created_at


@pytest.mark.integration
def test_close_releases_the_pool_and_is_idempotent(ledger):
    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])  # forces a real pool
    assert ledger._pool is not None

    ledger.close()
    assert ledger._pool is None

    ledger.close()  # must not raise on an already-closed / never-opened ledger


@pytest.mark.integration
def test_ledger_is_usable_again_after_close_transparently_reopens(ledger):
    """ADR-0011: `close()` resets `self._pool` to `None` rather than leaving
    a permanently-closed `ConnectionPool` behind — reuse after `close()`
    must construct a fresh pool, not raise `PoolClosed`."""
    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
    ledger.close()

    written = ledger.record_ingested("test-key-1", "tenant-a", "hash-b", ["c2"])  # must not raise

    assert written.version == 2


@pytest.mark.integration
def test_close_on_a_ledger_that_never_connected_is_a_safe_no_op():
    unused_ledger = PostgresLifecycleLedger(dsn=DSN)
    unused_ledger.close()  # no pool ever constructed — must not raise


@pytest.mark.integration
def test_check_health_reports_healthy_against_a_real_postgres(ledger):
    """Lot 6 (readiness and resilience). `ledger` fixture already ran
    `auto_migrate=True`, so the schema exists by the time this probes."""
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


@pytest.mark.integration
def test_check_health_reports_unhealthy_when_schema_not_migrated():
    """ADR-0011: against a database that is reachable but has never been
    migrated, check_health() must report unhealthy — not the previous
    behavior (implicit DDL made this state unreachable in practice)."""
    fresh_db_dsn = os.environ.get("MRAG_TEST_POSTGRES_UNMIGRATED_DSN")
    if not fresh_db_dsn:
        pytest.skip(
            "Set MRAG_TEST_POSTGRES_UNMIGRATED_DSN to a reachable but never-migrated "
            "database to run this test."
        )
    never_migrated = PostgresLifecycleLedger(dsn=fresh_db_dsn)

    results = never_migrated.check_health()

    assert results[0].healthy is False
    assert results[0].detail is not None
    assert "migrat" in results[0].detail.lower()


@pytest.mark.integration
def test_concurrent_record_ingested_on_the_same_key_never_loses_an_update(ledger):
    """Codex review HIGH-002 — the actual regression test the fix exists
    for. Before this fix, `record_ingested()` read the current version with
    `get()`, computed `version + 1` in Python, then wrote it back through a
    second, independently-pooled connection checkout: N concurrent calls
    for the same `document_key` could each read the same starting version
    and race to write the same next version, silently overwriting each
    other rather than each landing its own distinct version. The fix
    (`_UPSERT_INGEST`'s atomic `version = document_lifecycle.version + 1`)
    means N calls — even from N separate `PostgresLifecycleLedger`
    instances, each with its own pool, not just N threads sharing one — must
    produce N distinct, sequential versions with no gaps and no repeats."""
    from concurrent.futures import ThreadPoolExecutor

    n_calls = 20
    # Separate ledger *instances* (separate pools), not just separate
    # threads sharing `ledger` — proves the atomicity is a database-level
    # guarantee, not an artifact of one process's own connection pool.
    ledgers = [PostgresLifecycleLedger(dsn=DSN, auto_migrate=True) for _ in range(n_calls)]
    try:
        with ThreadPoolExecutor(max_workers=n_calls) as pool:
            results = list(
                pool.map(
                    lambda ledger_instance: ledger_instance.record_ingested(
                        "test-key-1", "tenant-a", "hash-a", ["c1"]
                    ),
                    ledgers,
                )
            )

        versions = sorted(r.version for r in results)
        assert versions == list(range(1, n_calls + 1))  # every version 1..N exactly once

        final = ledger.get("test-key-1")
        assert final.version == n_calls
    finally:
        for ledger_instance in ledgers:
            ledger_instance.close()


@pytest.mark.integration
def test_concurrent_tombstone_calls_on_the_same_key_are_safe(ledger):
    """A companion to the record_ingested() race test above: concurrent
    `tombstone()` calls on the same key must not raise or corrupt state —
    exactly one call observes the row and tombstones it; the rest see it
    already tombstoned and are safe no-ops (the `UPDATE` still matches the
    row — it is idempotent to re-apply the same tombstone state — so every
    call returns a record, not `None`, unlike a concurrent call racing a
    key that never existed at all)."""
    from concurrent.futures import ThreadPoolExecutor

    ledger.record_ingested("test-key-1", "tenant-a", "hash-a", ["c1"])
    n_calls = 10
    ledgers = [PostgresLifecycleLedger(dsn=DSN, auto_migrate=True) for _ in range(n_calls)]
    try:
        with ThreadPoolExecutor(max_workers=n_calls) as pool:
            results = list(
                pool.map(lambda ledger_instance: ledger_instance.tombstone("test-key-1"), ledgers)
            )

        assert all(r is not None for r in results)
        assert all(r.status == DocumentStatus.TOMBSTONED for r in results)
        final = ledger.get("test-key-1")
        assert final.status == DocumentStatus.TOMBSTONED
        assert final.chunk_ids == []
    finally:
        for ledger_instance in ledgers:
            ledger_instance.close()
