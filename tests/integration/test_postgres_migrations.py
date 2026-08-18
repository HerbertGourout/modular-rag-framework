"""Integration tests for adapters/postgres/migrations.py::MigrationRunner —
requires PostgreSQL on localhost:5432 (same "assumes a running local
service" convention as test_qdrant_store.py / test_postgres_audit_sink.py).
Not run by default — deselect with `-m "not integration"`.

Directly proves this lot's two acceptance criteria that unit tests (fakes,
no real database) cannot: "démarrage sur base vide via migrations" and
"upgrade d'un schéma existant testé."
"""
import os

import pytest

from modular_rag.adapters.postgres.migrations import MigrationRunner

DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)


def _drop_everything() -> None:
    """Reset to a genuinely empty state before each test — drops the two
    real tables and the runner's own bookkeeping table, so `migrate()` is
    exercised starting from nothing, not from whatever the previous test
    left behind."""
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS document_lifecycle CASCADE")
        conn.execute("DROP TABLE IF EXISTS audit_events CASCADE")
        conn.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")


@pytest.fixture()
def runner():
    _drop_everything()
    yield MigrationRunner(DSN)
    _drop_everything()


@pytest.mark.integration
def test_migrate_starts_cleanly_on_an_empty_database(runner):
    """"Démarrage sur base vide via migrations" — the core acceptance
    criterion this lot exists to satisfy."""
    applied = runner.migrate()

    assert applied == ["0001", "0002", "0003"]
    assert runner.applied_versions() == ["0001", "0002", "0003"]

    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        assert conn.execute("SELECT to_regclass('document_lifecycle')").fetchone()[0] is not None
        assert conn.execute("SELECT to_regclass('audit_events')").fetchone()[0] is not None


@pytest.mark.integration
def test_migrate_is_idempotent_on_a_database_already_at_the_latest_version(runner):
    runner.migrate()

    second_call_applied = runner.migrate()

    assert second_call_applied == []
    assert runner.applied_versions() == ["0001", "0002", "0003"]


@pytest.mark.integration
def test_migrate_upgrades_an_existing_schema_incrementally(runner):
    """"Upgrade d'un schéma existant testé" — simulates a database already
    on an older version by migrating only up to `0002`, then upgrading."""
    first_pass = runner.migrate(target="0002")
    assert first_pass == ["0001", "0002"]
    assert runner.applied_versions() == ["0001", "0002"]

    second_pass = runner.migrate()  # no target — apply everything still pending

    assert second_pass == ["0003"]
    assert runner.applied_versions() == ["0001", "0002", "0003"]


@pytest.mark.integration
def test_rollback_reverses_the_most_recently_applied_migration(runner):
    runner.migrate()

    rolled_back = runner.rollback(steps=1)

    assert rolled_back == ["0003"]
    assert runner.applied_versions() == ["0001", "0002"]
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        # 0003's down.sql only drops the timestamp index — audit_events itself
        # must still exist (0002 was not rolled back).
        assert conn.execute("SELECT to_regclass('audit_events')").fetchone()[0] is not None


@pytest.mark.integration
def test_rollback_multiple_steps_reverses_in_reverse_order(runner):
    runner.migrate()

    rolled_back = runner.rollback(steps=2)

    assert rolled_back == ["0003", "0002"]
    assert runner.applied_versions() == ["0001"]
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        assert conn.execute("SELECT to_regclass('audit_events')").fetchone()[0] is None
        assert conn.execute("SELECT to_regclass('document_lifecycle')").fetchone()[0] is not None


@pytest.mark.integration
def test_migrate_and_rollback_round_trip_leaves_no_trace(runner):
    """Schema reversibility, end to end: migrate everything, roll back
    everything, and the two real tables are gone again — same
    "genuinely empty" state `_drop_everything()` starts from."""
    runner.migrate()

    runner.rollback(steps=3)

    assert runner.applied_versions() == []
    import psycopg

    with psycopg.connect(DSN, autocommit=True) as conn:
        assert conn.execute("SELECT to_regclass('document_lifecycle')").fetchone()[0] is None
        assert conn.execute("SELECT to_regclass('audit_events')").fetchone()[0] is None


@pytest.mark.integration
def test_concurrent_migrate_calls_apply_each_migration_exactly_once(runner):
    """test-specialist review (pre-implementation): the `pg_advisory_xact_lock`
    guard exists specifically so two processes starting `auto_migrate=True`
    concurrently never race applying the same migration twice. Two runners
    against the same DSN, both calling migrate() from separate threads,
    prove the lock actually serializes them rather than merely existing."""
    from concurrent.futures import ThreadPoolExecutor

    runners = [MigrationRunner(DSN) for _ in range(5)]

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda r: r.migrate(), runners))

    total_applied_versions = [v for applied in results for v in applied]
    # Exactly one of the five concurrent calls actually applied each
    # migration; the other four found it already recorded and skipped it.
    assert sorted(total_applied_versions) == ["0001", "0002", "0003"]
    assert MigrationRunner(DSN).applied_versions() == ["0001", "0002", "0003"]
