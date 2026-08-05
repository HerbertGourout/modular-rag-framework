"""Unit tests for ingestion/lifecycle/backup.py — the verified restore
exercise for Lot 12c (docs/refactoring-plan.md: "including a verified
restore exercise, not just a backup that has never been tested").
"""
from __future__ import annotations

from modular_rag.contracts.lifecycle import DocumentStatus
from modular_rag.ingestion.lifecycle.backup import backup_ledger, restore_ledger
from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger


def test_backup_then_restore_round_trips_active_and_tombstoned_records():
    """The actual verified-restore exercise: back up a ledger with a mix of
    active and tombstoned records, restore into a *fresh* ledger instance,
    and prove the full state matches — not just that backup_ledger() runs
    without raising."""
    source = InMemoryLifecycleLedger()
    source.record_ingested("key-1", "acme-corp", "hash-a", ["c1", "c2"])
    source.record_ingested("key-2", "acme-corp", "hash-b", ["c3"])
    source.tombstone("key-2")

    backup = backup_ledger(source)

    target = InMemoryLifecycleLedger()  # fresh instance — proves this isn't a no-op
    assert target.get("key-1") is None  # sanity: genuinely empty before restore

    count = restore_ledger(target, backup)

    assert count == 2
    assert target.get("key-1") == source.get("key-1")
    assert target.get("key-2") == source.get("key-2")
    assert target.get("key-2").status == DocumentStatus.TOMBSTONED


def test_backup_of_an_empty_ledger_restores_to_empty():
    source = InMemoryLifecycleLedger()

    backup = backup_ledger(source)
    target = InMemoryLifecycleLedger()
    count = restore_ledger(target, backup)

    assert count == 0
    assert target.export_all() == []


def test_restore_does_not_bump_version_or_recompute_timestamps():
    """restore_record() writes verbatim — distinct from record_ingested()'s
    normal ingest-flow version-bumping."""
    source = InMemoryLifecycleLedger()
    original = source.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])

    backup = backup_ledger(source)
    target = InMemoryLifecycleLedger()
    restore_ledger(target, backup)

    restored = target.get("key-1")
    assert restored.version == original.version
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at
