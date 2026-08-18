-- ADR-0011: reverses 0003_audit_events_timestamp_index.up.sql.
DROP INDEX IF EXISTS idx_audit_events_timestamp;
