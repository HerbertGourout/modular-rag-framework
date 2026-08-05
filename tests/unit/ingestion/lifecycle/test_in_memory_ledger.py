"""Unit tests for ingestion/lifecycle/in_memory_ledger.py —
InMemoryLifecycleLedger. Lot 12a, docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.lifecycle import DocumentStatus
from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger


def test_get_returns_none_for_unknown_key():
    assert InMemoryLifecycleLedger().get("unknown") is None


def test_record_ingested_creates_a_new_record_at_version_1():
    ledger = InMemoryLifecycleLedger()

    record = ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1", "c2"])

    assert record.version == 1
    assert record.status == DocumentStatus.ACTIVE
    assert record.chunk_ids == ["c1", "c2"]
    assert ledger.get("key-1") == record


def test_record_ingested_again_bumps_the_version_and_preserves_created_at():
    ledger = InMemoryLifecycleLedger()
    first = ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])

    second = ledger.record_ingested("key-1", "acme-corp", "hash-b", ["c2", "c3"])

    assert second.version == 2
    assert second.content_hash == "hash-b"
    assert second.chunk_ids == ["c2", "c3"]
    assert second.created_at == first.created_at


def test_tombstone_marks_status_and_clears_chunk_ids():
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1", "c2"])

    record = ledger.tombstone("key-1")

    assert record is not None
    assert record.status == DocumentStatus.TOMBSTONED
    assert record.chunk_ids == []


def test_tombstone_returns_none_for_unknown_key():
    assert InMemoryLifecycleLedger().tombstone("unknown") is None


def test_name_reports_in_memory():
    assert InMemoryLifecycleLedger().name() == "in-memory"
