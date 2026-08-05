"""Lifecycle-ledger backup/restore (Lot 12c, docs/refactoring-plan.md —
"Implement backup, restore, rebuild-from-source, and right-to-erasure proof
(including a verified restore exercise, not just a backup that has never
been tested)").

This is a *ledger* backup — it serializes every `DocumentRecord`
(`export_all()`, including tombstoned ones — a backup that silently dropped
tombstone history would make right-to-erasure proof unverifiable after a
restore) to portable JSON, and restores it verbatim via `restore_record()`.

It is deliberately not a chunk-content or vector-embedding backup: this
ledger stores ids and hashes, never chunk content (Lot 12b's "no
fabrication" principle — see `orchestration/reconciliation.py`), so there is
no content here to back up in the first place. Restoring the ledger alone
does not restore indexed content; if the vector/lexical stores themselves
are lost, `rebuild_document()` (`orchestration/engine.py`) is what
regenerates their content, from original source documents, not from this
backup.

Production PostgreSQL-backed ledgers (`adapters.lifecycle.postgres_ledger.PostgresLifecycleLedger`)
should also rely on PostgreSQL's own `pg_dump`/`pg_restore` for
disaster-recovery-grade backups of the `document_lifecycle` table — this
module's JSON format is for portable, ledger-implementation-agnostic
snapshots (e.g. moving state from `InMemoryLifecycleLedger` during a test,
or a lightweight manual export), not a replacement for `pg_dump`.
"""
from __future__ import annotations

import json

from modular_rag.contracts.lifecycle import DocumentRecord, LifecycleLedger


def backup_ledger(ledger: LifecycleLedger) -> str:
    """Serialize every record (any status) to a JSON string."""
    records = ledger.export_all()
    return json.dumps([r.model_dump(mode="json") for r in records])


def restore_ledger(ledger: LifecycleLedger, backup: str) -> int:
    """Restore every record from a `backup_ledger()` JSON string. Returns the
    number of records restored. Each record is written verbatim via
    `restore_record()` — no version bump, no timestamp recomputation."""
    raw_records = json.loads(backup)
    for raw in raw_records:
        ledger.restore_record(DocumentRecord.model_validate(raw))
    return len(raw_records)
