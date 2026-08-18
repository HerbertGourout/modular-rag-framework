-- ADR-0011 (PostgreSQL migrations, pooling, and retention).
-- Extracted verbatim from the inline `_DDL` string previously run
-- unconditionally on every PostgresLifecycleLedger connection
-- (adapters/lifecycle/postgres_ledger.py) — schema unchanged, only the
-- mechanism that applies it.
CREATE TABLE IF NOT EXISTS document_lifecycle (
    document_key    TEXT PRIMARY KEY,
    tenant_id       TEXT,
    content_hash    TEXT NOT NULL,
    version         INTEGER NOT NULL,
    schema_version  TEXT NOT NULL,
    status          TEXT NOT NULL,
    chunk_ids       JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_document_lifecycle_tenant ON document_lifecycle (tenant_id);
