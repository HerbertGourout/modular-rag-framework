"""Concurrency tests for InMemoryLifecycleLedger's lock (Lot 14,
docs/refactoring-plan.md — "make ... mutable indexes concurrency-safe").
Real threads, not simulated — proves the lock actually prevents the lost-
update race `record_ingested()`'s read-then-write is exposed to.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger


def test_concurrent_record_ingested_on_the_same_key_never_loses_an_update():
    """50 threads each call record_ingested() once for the same document_key.
    Without the lock, concurrent read-then-write on `version` can lose
    updates (two threads both read version=N, both write version=N+1). With
    the lock, exactly 50 sequential versions must be produced — no two
    calls can observe the same "existing" state.
    """
    ledger = InMemoryLifecycleLedger()
    n = 50

    def ingest(i: int):
        return ledger.record_ingested("key-1", "acme-corp", f"hash-{i}", [f"c{i}"])

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(ingest, range(n)))

    versions = sorted(r.version for r in results)
    assert versions == list(range(1, n + 1))  # every version 1..50 produced exactly once
    assert ledger.get("key-1").version == n


def test_concurrent_record_ingested_on_different_keys_all_succeed():
    ledger = InMemoryLifecycleLedger()
    n = 50

    def ingest(i: int):
        ledger.record_ingested(f"key-{i}", "acme-corp", f"hash-{i}", [f"c{i}"])

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(ingest, range(n)))

    assert len(ledger.export_all()) == n
