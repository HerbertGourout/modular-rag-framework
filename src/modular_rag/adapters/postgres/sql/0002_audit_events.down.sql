-- ADR-0011: reverses 0002_audit_events.up.sql. Destructive — drops all audit
-- history. "Reasonable rollback" for this lot means schema reversibility,
-- not data preservation; back up first (docs/guides/backup-restore.md), and
-- note that dropping a compliance audit trail may itself have retention/legal
-- implications outside this tool's scope.
DROP INDEX IF EXISTS idx_audit_events_correlation;
DROP INDEX IF EXISTS idx_audit_events_tenant;
DROP TABLE IF EXISTS audit_events;
