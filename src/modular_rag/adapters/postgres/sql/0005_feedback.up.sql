-- ADR-0014 (Batch 14 — feedback, drift, and human review).
-- Mirrors 0002_audit_events.up.sql's shape. `expires_at` is a plain column,
-- not GENERATED — computed in Python at insert time, same lesson as
-- 0004_audit_events_expires_at.up.sql (timestamptz + interval arithmetic is
-- STABLE, not IMMUTABLE, so PostgreSQL rejects it as a generated-column
-- expression).
--
-- The uniqueness on idempotency_key is scoped per tenant via a
-- COALESCE(tenant_id, '')-expression unique index, not a bare column
-- constraint: `idempotency_key` is a client-supplied, untrusted value
-- (api/__init__.py's FeedbackRequest.idempotency_key), and a bare
-- `UNIQUE (idempotency_key)` would let one authenticated tenant pre-claim
-- another tenant's key, silently swallowing that tenant's genuine feedback
-- via ON CONFLICT DO NOTHING (security review finding, Batch 14 pass 1).
CREATE TABLE IF NOT EXISTS feedback (
    id                TEXT PRIMARY KEY,
    schema_version    TEXT NOT NULL,
    trace_id          TEXT NOT NULL,
    tenant_id         TEXT,
    rating            TEXT,
    correction_text   TEXT,
    citation_count    INTEGER,
    idempotency_key   TEXT NOT NULL,
    submitted_by      TEXT,
    is_test           BOOLEAN NOT NULL DEFAULT FALSE,
    retention_days    INTEGER NOT NULL,
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_feedback_tenant_idempotency
    ON feedback (COALESCE(tenant_id, ''), idempotency_key);
CREATE INDEX IF NOT EXISTS idx_feedback_trace_id ON feedback (trace_id);
CREATE INDEX IF NOT EXISTS idx_feedback_tenant ON feedback (tenant_id);
CREATE INDEX IF NOT EXISTS idx_feedback_expires_at ON feedback (expires_at);
