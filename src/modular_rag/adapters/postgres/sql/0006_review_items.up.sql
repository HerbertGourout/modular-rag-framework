-- ADR-0014 (Batch 14 — feedback, drift, and human review).
-- Durable backend for contracts.review.ReviewItem
-- (adapters.review.postgres_queue.PostgresReviewQueue). `resolved`/
-- `approved`/`reviewer` are the one mutable part of this table (a review
-- item's resolution) — unlike audit_events/feedback, this table is not
-- purely append-only: `PostgresReviewQueue.resolve()` issues a real UPDATE.
-- `expires_at` follows the same computed-in-Python pattern as
-- 0005_feedback.up.sql.
CREATE TABLE IF NOT EXISTS review_items (
    id                TEXT PRIMARY KEY,
    answer_id         TEXT NOT NULL,
    query_id          TEXT NOT NULL,
    tenant_id         TEXT,
    reason            TEXT NOT NULL,
    confidence        DOUBLE PRECISION,
    created_at        TIMESTAMPTZ NOT NULL,
    resolved          BOOLEAN NOT NULL DEFAULT FALSE,
    approved          BOOLEAN,
    reviewer          TEXT,
    retention_days    INTEGER NOT NULL,
    expires_at        TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_items_tenant ON review_items (tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_items_resolved ON review_items (resolved);
CREATE INDEX IF NOT EXISTS idx_review_items_expires_at ON review_items (expires_at);
