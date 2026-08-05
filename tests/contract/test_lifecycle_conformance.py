"""Semantic conformance tests for the LifecycleLedger port
(contracts/lifecycle.py). Lot 12a, docs/refactoring-plan.md.

Parametrized over `InMemoryLifecycleLedger` only.
`PostgresLifecycleLedger` (adapters/lifecycle/postgres_ledger.py) is
excluded here for the same reason `test_audit_conformance.py` excludes
`PostgresAuditSink` — it requires a real external service. Covered instead
by `tests/integration/test_postgres_lifecycle_ledger.py`
(`@pytest.mark.integration`).
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.lifecycle import DocumentStatus, LifecycleLedger
from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger

LEDGERS = [InMemoryLifecycleLedger]


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_ledger_satisfies_the_protocol(ledger_factory: type) -> None:
    assert isinstance(ledger_factory(), LifecycleLedger)


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_get_is_none_before_any_ingest(ledger_factory: type) -> None:
    assert ledger_factory().get("key-1") is None


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_record_ingested_then_get_round_trips(ledger_factory: type) -> None:
    ledger = ledger_factory()

    written = ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])
    read = ledger.get("key-1")

    assert read == written


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_second_record_ingested_call_bumps_version(ledger_factory: type) -> None:
    ledger = ledger_factory()
    ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])

    second = ledger.record_ingested("key-1", "acme-corp", "hash-b", ["c2"])

    assert second.version == 2


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_tombstone_sets_status_and_clears_chunk_ids(ledger_factory: type) -> None:
    ledger = ledger_factory()
    ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])

    record = ledger.tombstone("key-1")

    assert record is not None
    assert record.status == DocumentStatus.TOMBSTONED
    assert record.chunk_ids == []


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_ledger_has_a_name(ledger_factory: type) -> None:
    assert ledger_factory().name()


@pytest.mark.parametrize("ledger_factory", LEDGERS)
def test_list_active_excludes_tombstoned_records(ledger_factory: type) -> None:
    ledger = ledger_factory()
    ledger.record_ingested("key-1", "acme-corp", "hash-a", ["c1"])
    ledger.record_ingested("key-2", "acme-corp", "hash-b", ["c2"])
    ledger.tombstone("key-2")

    active = ledger.list_active()

    assert {r.document_key for r in active} == {"key-1"}
