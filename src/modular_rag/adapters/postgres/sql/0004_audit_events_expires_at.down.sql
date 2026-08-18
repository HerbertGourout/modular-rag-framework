-- ADR-0011: reverses 0004_audit_events_expires_at.up.sql. Dropping the
-- column also drops its index automatically (PostgreSQL removes an index
-- whose sole underlying column is dropped) — no separate DROP INDEX needed,
-- but included explicitly for symmetry with 0003's down-script and to be
-- correct even if a future PostgreSQL version changes that behavior.
DROP INDEX IF EXISTS idx_audit_events_expires_at;
ALTER TABLE audit_events DROP COLUMN IF EXISTS expires_at;
