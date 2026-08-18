-- ADR-0011: reverses 0001_document_lifecycle.up.sql. Destructive — drops all
-- lifecycle-ledger data. "Reasonable rollback" for this lot means schema
-- reversibility, not data preservation; back up first (docs/guides/backup-restore.md).
DROP INDEX IF EXISTS idx_document_lifecycle_tenant;
DROP TABLE IF EXISTS document_lifecycle;
