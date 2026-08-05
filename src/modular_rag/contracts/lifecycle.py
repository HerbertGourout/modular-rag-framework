"""Document lifecycle contract (Lot 12a, docs/refactoring-plan.md — "Define
document identity, idempotent ingestion, update, deletion, and tombstone
semantics. This is the domain-level lifecycle contract, independent of any
specific index implementation.").

A `DocumentRecord` tracks one logical document's current indexed state —
its content hash (to detect real changes vs. re-ingesting identical
content), version, status, and the ids of the chunks currently indexed for
it (so a later update/delete knows exactly what to remove before/instead of
re-indexing). Distinct from `contracts.audit.AuditEvent`: an audit event is
an immutable record of something that happened; a `DocumentRecord` is
mutable current state, updated in place as a document's lifecycle
progresses.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    TOMBSTONED = "tombstoned"


class DocumentRecord(BaseModel):
    document_key: str
    tenant_id: str | None = None
    content_hash: str
    version: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE
    chunk_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class LifecycleLedger(Protocol):
    """Track document identity/version/status independent of any specific
    index. `ingestion.lifecycle.in_memory_ledger.InMemoryLifecycleLedger` is
    the reference implementation; `adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`
    is the durable backend (Lot 12a, PostgreSQL — consistent with Lot 10's
    audit-store choice). Registered on `Container.lifecycle_ledger` —
    optional, mirrors every other optional component's precedent.

    Deliberately split into `get()` (read, to decide skip/update *before*
    chunking) and `record_ingested()` (write, called *after* chunking and
    indexing succeed) rather than one atomic "upsert-and-tell-me-if-it-
    changed" call — the caller (`RAGEngine.ingest()`) needs the old record's
    `chunk_ids` to delete stale chunks before it can safely call
    `record_ingested()` with the new ones.
    """

    def get(self, document_key: str) -> DocumentRecord | None: ...

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord: ...

    def tombstone(self, document_key: str) -> DocumentRecord | None: ...

    def name(self) -> str: ...
