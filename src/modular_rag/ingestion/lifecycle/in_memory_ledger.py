"""In-memory LifecycleLedger reference implementation (Lot 12a,
docs/refactoring-plan.md). A real, working ledger — not a mock — for tests
and local/dev use before a durable backend
(`adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`) is configured.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from modular_rag.contracts.lifecycle import DocumentRecord, DocumentStatus


class InMemoryLifecycleLedger:
    """Guarded by a `threading.Lock` (Lot 14, docs/refactoring-plan.md —
    "make ... mutable indexes concurrency-safe"): `record_ingested()` is a
    read-then-write (read the existing version, write version+1) — a real
    race under concurrent calls for the *same* `document_key` without a
    lock, unlike a single dict assignment."""

    def __init__(self) -> None:
        self._records: dict[str, DocumentRecord] = {}
        self._lock = threading.Lock()

    def get(self, document_key: str) -> DocumentRecord | None:
        with self._lock:
            return self._records.get(document_key)

    def list_active(self) -> list[DocumentRecord]:
        with self._lock:
            return [r for r in self._records.values() if r.status == DocumentStatus.ACTIVE]

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord:
        with self._lock:
            existing = self._records.get(document_key)
            version = existing.version + 1 if existing else 1
            now = datetime.now(UTC)
            record = DocumentRecord(
                document_key=document_key,
                tenant_id=tenant_id,
                content_hash=content_hash,
                version=version,
                status=DocumentStatus.ACTIVE,
                chunk_ids=list(chunk_ids),
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._records[document_key] = record
            return record

    def tombstone(self, document_key: str) -> DocumentRecord | None:
        with self._lock:
            existing = self._records.get(document_key)
            if existing is None:
                return None
            record = existing.model_copy(
                update={
                    "status": DocumentStatus.TOMBSTONED,
                    "chunk_ids": [],
                    "updated_at": datetime.now(UTC),
                }
            )
            self._records[document_key] = record
            return record

    def export_all(self) -> list[DocumentRecord]:
        with self._lock:
            return list(self._records.values())

    def restore_record(self, record: DocumentRecord) -> None:
        with self._lock:
            self._records[record.document_key] = record

    def name(self) -> str:
        return "in-memory"
