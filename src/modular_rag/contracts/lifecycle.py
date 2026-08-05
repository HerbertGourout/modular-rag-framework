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

INDEX_SCHEMA_VERSION = "1.0"  # bumped when the *shape* of what's indexed changes in a
# way reconciliation/migration needs to know about (e.g. embedding dimension change,
# chunk field additions that affect indexing). Lot 12b, docs/refactoring-plan.md —
# "Define index schema/version." Carried per-record, not globally, so a ledger can hold
# documents indexed under different schema versions during a rolling migration.


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    TOMBSTONED = "tombstoned"


class DocumentRecord(BaseModel):
    document_key: str
    tenant_id: str | None = None
    content_hash: str
    version: int = 1
    schema_version: str = INDEX_SCHEMA_VERSION
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

    def list_active(self) -> list[DocumentRecord]:
        """Enumerate every `ACTIVE` record. Added in Lot 12b
        (docs/refactoring-plan.md) so `orchestration.reconciliation.IndexReconciler`
        can check the whole corpus, not just one document at a time — `get()`
        alone can't answer "what should be indexed right now" across every
        document."""
        ...

    def record_ingested(
        self,
        document_key: str,
        tenant_id: str | None,
        content_hash: str,
        chunk_ids: list[str],
    ) -> DocumentRecord: ...

    def tombstone(self, document_key: str) -> DocumentRecord | None: ...

    def export_all(self) -> list[DocumentRecord]:
        """Every record regardless of status — including `TOMBSTONED` ones,
        unlike `list_active()`. Added in Lot 12c (docs/refactoring-plan.md)
        for `ingestion.lifecycle.backup.backup_ledger()`: a backup that
        silently dropped tombstone history would make right-to-erasure proof
        unverifiable after a restore."""
        ...

    def restore_record(self, record: DocumentRecord) -> None:
        """Write a record back exactly as given — no version bump, no
        `created_at`/`updated_at` recomputation, unlike `record_ingested()`
        (which is for the normal ingest flow, not restore). Added in
        Lot 12c for `ingestion.lifecycle.backup.restore_ledger()`."""
        ...

    def name(self) -> str: ...
