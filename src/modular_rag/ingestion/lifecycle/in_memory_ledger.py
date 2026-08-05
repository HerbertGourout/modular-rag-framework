"""In-memory LifecycleLedger reference implementation (Lot 12a,
docs/refactoring-plan.md). A real, working ledger — not a mock — for tests
and local/dev use before a durable backend
(`adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`) is configured.
"""
from __future__ import annotations

from datetime import UTC, datetime

from modular_rag.contracts.lifecycle import DocumentRecord, DocumentStatus


class InMemoryLifecycleLedger:
    def __init__(self) -> None:
        self._records: dict[str, DocumentRecord] = {}

    def get(self, document_key: str) -> DocumentRecord | None:
        return self._records.get(document_key)

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord:
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

    def name(self) -> str:
        return "in-memory"
