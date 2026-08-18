-- ADR-0011 (PostgreSQL migrations, pooling, and retention).
-- Extracted verbatim from the inline `_DDL` string previously run
-- unconditionally on every PostgresAuditSink connection
-- (adapters/audit/postgres_sink.py) — schema unchanged, only the mechanism
-- that applies it. See docs/guides/postgres-permissions.md before granting
-- CREATE on this schema to the application's normal runtime role: DDL
-- ownership belongs to the migration role, not the INSERT/SELECT-only app
-- role that connects for real traffic.
CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    causation_id    TEXT,
    tenant_id       TEXT NOT NULL,
    actor           TEXT,
    "timestamp"     TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,
    retention_days  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant ON audit_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_correlation ON audit_events (correlation_id);
