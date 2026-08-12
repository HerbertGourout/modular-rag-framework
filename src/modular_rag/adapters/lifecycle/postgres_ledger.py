"""PostgreSQL-backed LifecycleLedger (Lot 12a, docs/refactoring-plan.md — "The
lifecycle/idempotency ledger itself is backed by PostgreSQL, consistent with
Lot 10's audit-store choice.").

`psycopg` is imported lazily per `.claude/.instructions.md` §4 — not
declared in `pyproject.toml`, same "opt-in infrastructure" precedent as
`adapters/audit/postgres_sink.py` (Lot 10). Install with:
`pip install psycopg[binary]>=3.1`.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from modular_rag.contracts.lifecycle import INDEX_SCHEMA_VERSION, DocumentRecord, DocumentStatus
from modular_rag.core.errors import StorageError

if TYPE_CHECKING:
    import psycopg

# Mutable ledger, unlike the audit store's append-only table: a document's
# row is updated in place as its version/status changes. `updated_at` is the
# authoritative "last changed" marker; history across versions is not kept
# here — that's what the audit trail (Lot 10) is for.
_DDL = """
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
"""

_SELECT = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle WHERE document_key = %s
"""

_SELECT_ACTIVE = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle WHERE status = %s
"""

_SELECT_ALL = """
SELECT document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
       created_at, updated_at
FROM document_lifecycle
"""

_UPSERT = """
INSERT INTO document_lifecycle
    (document_key, tenant_id, content_hash, version, schema_version, status, chunk_ids,
     created_at, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (document_key) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    content_hash = EXCLUDED.content_hash,
    version = EXCLUDED.version,
    schema_version = EXCLUDED.schema_version,
    status = EXCLUDED.status,
    chunk_ids = EXCLUDED.chunk_ids,
    updated_at = EXCLUDED.updated_at
"""


class PostgresLifecycleLedger:
    """Durable `LifecycleLedger` backed by a single PostgreSQL table. Requires
    a reachable PostgreSQL instance — see
    `tests/integration/test_postgres_lifecycle_ledger.py`
    (`@pytest.mark.integration`, same convention as
    `tests/integration/test_postgres_audit_sink.py`, Lot 10).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: psycopg.Connection[Any] | None = None

    def _get_connection(self) -> psycopg.Connection[Any]:
        if self._conn is None:
            try:
                import psycopg
            except ImportError as exc:
                raise ImportError(
                    "psycopg is required for PostgresLifecycleLedger. "
                    "Install it with: pip install psycopg[binary]>=3.1"
                ) from exc
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            self._conn.execute(_DDL)
        return self._conn

    def get(self, document_key: str) -> DocumentRecord | None:
        conn = self._get_connection()
        try:
            row = conn.execute(_SELECT, (document_key,)).fetchone()
        except Exception as exc:
            raise StorageError(f"Failed to read document_key={document_key!r}: {exc}") from exc
        if row is None:
            return None
        return self._row_to_record(row)

    def list_active(self) -> list[DocumentRecord]:
        conn = self._get_connection()
        try:
            rows = conn.execute(_SELECT_ACTIVE, (DocumentStatus.ACTIVE.value,)).fetchall()
        except Exception as exc:
            raise StorageError(f"Failed to list active documents: {exc}") from exc
        return [self._row_to_record(row) for row in rows]

    def export_all(self) -> list[DocumentRecord]:
        conn = self._get_connection()
        try:
            rows = conn.execute(_SELECT_ALL).fetchall()
        except Exception as exc:
            raise StorageError(f"Failed to export document_lifecycle: {exc}") from exc
        return [self._row_to_record(row) for row in rows]

    def restore_record(self, record: DocumentRecord) -> None:
        self._write(record)

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord:
        existing = self.get(document_key)
        version = existing.version + 1 if existing else 1
        now = datetime.now(existing.updated_at.tzinfo) if existing else datetime.now().astimezone()
        record = DocumentRecord(
            document_key=document_key,
            tenant_id=tenant_id,
            content_hash=content_hash,
            version=version,
            schema_version=INDEX_SCHEMA_VERSION,
            status=DocumentStatus.ACTIVE,
            chunk_ids=list(chunk_ids),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._write(record)
        return record

    def tombstone(self, document_key: str) -> DocumentRecord | None:
        existing = self.get(document_key)
        if existing is None:
            return None
        record = existing.model_copy(
            update={
                "status": DocumentStatus.TOMBSTONED,
                "chunk_ids": [],
                "updated_at": datetime.now(existing.updated_at.tzinfo),
            }
        )
        self._write(record)
        return record

    def _write(self, record: DocumentRecord) -> None:
        conn = self._get_connection()
        try:
            conn.execute(
                _UPSERT,
                (
                    record.document_key,
                    record.tenant_id,
                    record.content_hash,
                    record.version,
                    record.schema_version,
                    record.status.value,
                    json.dumps(record.chunk_ids),
                    record.created_at,
                    record.updated_at,
                ),
            )
        except Exception as exc:
            raise StorageError(
                f"Failed to write document_key={record.document_key!r}: {exc}"
            ) from exc

    @staticmethod
    def _row_to_record(row: tuple[Any, ...]) -> DocumentRecord:
        (
            document_key,
            tenant_id,
            content_hash,
            version,
            schema_version,
            status,
            chunk_ids,
            created_at,
            updated_at,
        ) = row
        return DocumentRecord(
            document_key=document_key,
            tenant_id=tenant_id,
            content_hash=content_hash,
            version=version,
            schema_version=schema_version,
            status=DocumentStatus(status),
            chunk_ids=list(chunk_ids),
            created_at=created_at,
            updated_at=updated_at,
        )

    def name(self) -> str:
        return "postgres"

    def close(self) -> None:
        """Release the underlying connection, if one was ever opened.

        Same gap, same fix as `adapters/audit/postgres_sink.py::PostgresAuditSink.close()`
        (Codex review, MED-003): without this, `Container.close()`'s
        `getattr(component, "close", None)` discovery silently found nothing to call,
        leaking this ledger's connection on every `app.close()`. Idempotent.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
