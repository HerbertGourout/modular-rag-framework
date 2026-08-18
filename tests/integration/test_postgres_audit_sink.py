"""Integration tests for PostgresAuditSink — requires PostgreSQL on
localhost:5432 (same "assumes a running local service" convention as
test_qdrant_store.py). Not run by default — deselect with `-m "not integration"`.

ADR-0011 (PostgreSQL migrations, connection pooling, and audit retention):
`auto_migrate=True` replaces the retired implicit-DDL-on-connect behavior —
every fixture below runs against a fresh or existing schema either way.
`_get_connection()` (referenced by this file before this change) never
existed on the real class; the real accessor is `_get_pool()`, returning a
`psycopg_pool.ConnectionPool`.
"""
import os
from datetime import UTC, datetime, timedelta

import pytest

from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
from modular_rag.contracts.audit import AuditEvent, AuditEventType
from modular_rag.core.errors import SecurityError

DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture()
def sink():
    s = PostgresAuditSink(dsn=DSN, auto_migrate=True)
    with s._get_pool().connection() as conn:
        conn.execute("DELETE FROM audit_events WHERE tenant_id = 'test-tenant'")
    try:
        yield s
    finally:
        with s._get_pool().connection() as conn:
            conn.execute("DELETE FROM audit_events WHERE tenant_id = 'test-tenant'")
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

    with sink._get_pool().connection() as conn:
        row = conn.execute(
            "SELECT id, event_type, tenant_id, payload FROM audit_events WHERE id = %s",
            (event.id,),
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

    with sink._get_pool().connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit_events WHERE id = %s", (event.id,)
        ).fetchone()[0]
    assert count == 1


@pytest.mark.integration
def test_name_reports_postgres(sink):
    assert sink.name() == "postgres"


@pytest.mark.integration
def test_close_releases_the_pool_and_is_idempotent(sink):
    sink.record(_event())  # force a real pool to actually exist first
    assert sink._pool is not None

    sink.close()
    assert sink._pool is None

    sink.close()  # must not raise on an already-closed / never-opened sink


@pytest.mark.integration
def test_sink_is_usable_again_after_close_transparently_reopens(sink):
    """ADR-0011: `close()` resets `self._pool` to `None` rather than leaving
    a permanently-closed `ConnectionPool` behind — reuse after `close()`
    must construct a fresh pool, not raise `PoolClosed`."""
    sink.record(_event(correlation_id="corr-before-close"))
    sink.close()

    sink.record(_event(correlation_id="corr-after-close"))  # must not raise

    with sink._get_pool().connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit_events WHERE tenant_id = 'test-tenant'"
        ).fetchone()[0]
    assert count == 2


@pytest.mark.integration
def test_close_on_a_sink_that_never_connected_is_a_safe_no_op():
    unused_sink = PostgresAuditSink(dsn=DSN)
    unused_sink.close()  # no pool ever constructed — must not raise


@pytest.mark.integration
def test_check_health_reports_healthy_against_a_real_postgres(sink):
    """Lot 6 (readiness and resilience). `sink` fixture already ran
    `auto_migrate=True`, so the schema exists by the time this probes."""
    results = sink.check_health()

    assert len(results) == 1
    assert results[0].name == "postgres"
    assert results[0].healthy is True


@pytest.mark.integration
def test_check_health_reports_unhealthy_against_an_unreachable_postgres():
    unreachable = PostgresAuditSink(
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
    never_migrated = PostgresAuditSink(dsn=fresh_db_dsn)

    results = never_migrated.check_health()

    assert results[0].healthy is False
    assert results[0].detail is not None
    assert "migrat" in results[0].detail.lower()


@pytest.mark.integration
def test_count_expired_and_purge_expired_round_trip(sink):
    """ADR-0011: an event whose retention window has already elapsed is
    reported by count_expired() and removed by purge_expired(); an event
    still within its window is left alone."""
    now = datetime.now(UTC)
    expired = _event(
        correlation_id="corr-expired",
        timestamp=now - timedelta(days=400),
        retention_days=365,
    )
    still_valid = _event(correlation_id="corr-valid", timestamp=now, retention_days=365)
    sink.record(expired)
    sink.record(still_valid)

    assert sink.count_expired(now=now) == 1

    purging_sink = PostgresAuditSink(dsn=DSN, allow_purge=True)
    try:
        deleted = purging_sink.purge_expired(now=now)
    finally:
        purging_sink.close()

    assert deleted >= 1
    with sink._get_pool().connection() as conn:
        remaining_ids = {
            row[0]
            for row in conn.execute(
                "SELECT id FROM audit_events WHERE tenant_id = 'test-tenant'"
            ).fetchall()
        }
    assert expired.id not in remaining_ids
    assert still_valid.id in remaining_ids


@pytest.mark.integration
def test_purge_expired_refuses_without_allow_purge(sink):
    with pytest.raises(SecurityError):
        sink.purge_expired()


@pytest.mark.integration
def test_concurrent_purges_never_overcount_or_double_delete(sink):
    """Codex review MEDIUM-002 — the actual regression test the fix exists
    for. Before this fix, select-and-delete were two independent autocommit
    statements: two concurrent purge_expired() calls could both SELECT the
    same batch, the first DELETE would remove it, and the second DELETE
    (targeting already-deleted ids) would affect zero rows while its caller
    still counted the SELECT's row count — over-reporting how many rows
    were actually removed. The fix (one atomic `FOR UPDATE SKIP LOCKED` +
    `DELETE ... RETURNING` statement) means: the sum of what N concurrent
    purge calls each *report* deleting must equal the number of rows that
    actually disappeared from the table — never more (over-count) and never
    less (a row silently missed)."""
    from concurrent.futures import ThreadPoolExecutor

    now = datetime.now(UTC)
    expired_events = [
        _event(correlation_id=f"corr-expired-{i}", timestamp=now - timedelta(days=400))
        for i in range(50)
    ]
    for event in expired_events:
        sink.record(event)

    n_purgers = 5
    purging_sinks = [PostgresAuditSink(dsn=DSN, allow_purge=True) for _ in range(n_purgers)]
    try:
        with ThreadPoolExecutor(max_workers=n_purgers) as pool:
            reported_counts = list(
                pool.map(lambda purging_sink: purging_sink.purge_expired(now=now), purging_sinks)
            )
    finally:
        for purging_sink in purging_sinks:
            purging_sink.close()

    with sink._get_pool().connection() as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM audit_events WHERE tenant_id = 'test-tenant'"
        ).fetchone()[0]

    assert sum(reported_counts) == 50  # exactly the number actually deleted, no over/under-count
    assert remaining == 0


@pytest.mark.integration
def test_purge_expired_query_uses_the_expires_at_index(sink):
    """Codex review MEDIUM-003 — the actual performance check the fix
    exists for. `EXPLAIN` must show `idx_audit_events_expires_at` (0004's
    index on the now-plain, application-populated `expires_at` column) is
    *usable*, confirming the predicate is genuinely sargable now (the
    original `"timestamp" + make_interval(...)` predicate could never use
    `idx_audit_events_timestamp`, 0003's plain index on the bare column,
    regardless of how large the table grew).

    Codex review, remaining-risks item (second post-implementation pass):
    the first version of this test inserted only 200 rows and asserted the
    index name appears in the plan outright — the planner's actual choice
    between a sequential scan and an index scan depends on table size,
    `ANALYZE` statistics, and cost estimates, none of which this test
    controls; a small table can make PostgreSQL correctly prefer a
    sequential scan even with a perfectly usable index, which would make
    this test flap between pass and fail for reasons unrelated to whether
    the fix is correct. `SET LOCAL enable_seqscan = OFF` (scoped to this
    transaction only, via a `with conn.transaction():` block, and never
    touching the shared pool's other connections) forces the planner to
    prefer any usable index over a sequential scan, which is the standard
    technique for testing "is this index usable" independent of dataset
    size — the property this fix actually guarantees, not "is this index
    chosen by default for this particular row count."
    """
    now = datetime.now(UTC)
    for i in range(200):
        sink.record(
            _event(correlation_id=f"corr-explain-{i}", timestamp=now - timedelta(days=400))
        )

    with sink._get_pool().connection() as conn, conn.transaction():
        conn.execute("SET LOCAL enable_seqscan = OFF")
        plan_rows = conn.execute(
            "EXPLAIN SELECT id FROM audit_events "
            "WHERE retention_days > 0 AND expires_at < %s "
            "ORDER BY id LIMIT 500",
            (now,),
        ).fetchall()

    plan_text = "\n".join(row[0] for row in plan_rows)
    assert "idx_audit_events_expires_at" in plan_text, (
        f"expected idx_audit_events_expires_at to be usable, got plan:\n{plan_text}"
    )
