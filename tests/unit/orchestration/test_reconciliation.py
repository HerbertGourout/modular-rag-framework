"""Unit tests for orchestration/reconciliation.py — IndexReconciler. Lot 12b,
docs/refactoring-plan.md.

Uses real InMemoryLifecycleLedger + fake indexer/retriever (index/delete/
list_ids-shaped, matching the same fakes used in test_engine.py) so the
tests exercise the reconciler's actual divergence logic, not a mocked
shortcut.
"""
from __future__ import annotations

import pytest

from modular_rag.app.container import Container
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import ConfigurationError
from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger
from modular_rag.orchestration.reconciliation import IndexReconciler


class _FakeIndexer:
    def __init__(self, ids: list[str] | None = None) -> None:
        self._ids: set[str] = set(ids or [])

    def index(self, chunks) -> None:  # type: ignore[no-untyped-def]
        self._ids.update(c.id for c in chunks)

    def delete(self, ids: list[str]) -> None:
        self._ids -= set(ids)

    def clear(self) -> None:
        self._ids = set()

    def list_ids(self) -> list[str]:
        return sorted(self._ids)

    def name(self) -> str:
        return "fake-indexer"


class _FakeRetriever:
    def __init__(self, ids: list[str] | None = None) -> None:
        self._ids: set[str] = set(ids or [])

    def retrieve(self, query, k: int = 10):  # type: ignore[no-untyped-def]
        return []

    async def aretrieve(self, query, k: int = 10):  # type: ignore[no-untyped-def]
        return []

    def delete(self, ids: list[str]) -> None:
        self._ids -= set(ids)

    def list_ids(self) -> list[str]:
        return sorted(self._ids)

    def name(self) -> str:
        return "fake-retriever"


class _RetrieverWithoutListIds:
    """Duck-typed minimum Retriever — no list_ids()/delete(), matching a
    real Retriever implementation that doesn't opt into reconciliation."""

    def retrieve(self, query, k: int = 10):  # type: ignore[no-untyped-def]
        return []

    async def aretrieve(self, query, k: int = 10):  # type: ignore[no-untyped-def]
        return []

    def name(self) -> str:
        return "minimal-retriever"


def _container(
    indexer: _FakeIndexer, retriever, lifecycle_ledger=None  # type: ignore[no-untyped-def]
) -> Container:
    manifest = PipelineManifest(
        id="reconciliation-test",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", object())
    container.register("indexer", indexer)
    container.register("retriever", retriever)
    container.register("generator", object())
    if lifecycle_ledger is not None:
        container.register("lifecycle_ledger", lifecycle_ledger)
    return container


def test_check_without_a_lifecycle_ledger_raises() -> None:
    container = _container(_FakeIndexer(), _FakeRetriever())
    reconciler = IndexReconciler(container)

    with pytest.raises(ConfigurationError):
        reconciler.check()


def test_check_reports_clean_when_everything_matches() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1", "c2"])
    indexer = _FakeIndexer(ids=["c1", "c2"])
    retriever = _FakeRetriever(ids=["c1", "c2"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))

    report = reconciler.check()

    assert report.is_clean is True
    assert report.documents_checked == 1


def test_check_detects_a_chunk_missing_from_the_vector_index() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1", "c2"])
    indexer = _FakeIndexer(ids=["c1"])  # c2 missing
    retriever = _FakeRetriever(ids=["c1", "c2"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))

    report = reconciler.check()

    assert report.is_clean is False
    assert len(report.divergences) == 1
    assert report.divergences[0].document_key == "doc-1"
    assert report.divergences[0].missing_in_vector == ["c2"]
    assert report.divergences[0].missing_in_lexical == []


def test_check_detects_a_chunk_missing_from_the_lexical_index() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1", "c2"])
    indexer = _FakeIndexer(ids=["c1", "c2"])
    retriever = _FakeRetriever(ids=["c1"])  # c2 missing
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))

    report = reconciler.check()

    assert report.divergences[0].missing_in_lexical == ["c2"]


def test_check_detects_orphaned_ids_in_both_stores() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1"])
    indexer = _FakeIndexer(ids=["c1", "orphan-vector"])
    retriever = _FakeRetriever(ids=["c1", "orphan-lexical"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))

    report = reconciler.check()

    assert report.orphaned_in_vector == ["orphan-vector"]
    assert report.orphaned_in_lexical == ["orphan-lexical"]


def test_check_ignores_tombstoned_documents_expected_chunks() -> None:
    """A tombstoned document's chunk_ids are cleared by tombstone() itself
    (Lot 12a), so anything still present under its old ids in a store is
    correctly seen as orphaned, not as "missing" for a document that no
    longer expects anything."""
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1"])
    ledger.tombstone("doc-1")
    indexer = _FakeIndexer(ids=["c1"])  # stale leftover, not cleaned up
    retriever = _FakeRetriever(ids=["c1"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))

    report = reconciler.check()

    assert report.documents_checked == 0  # tombstoned, not active
    assert report.orphaned_in_vector == ["c1"]
    assert report.orphaned_in_lexical == ["c1"]


def test_check_treats_a_retriever_without_list_ids_as_having_nothing_indexed() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1"])
    indexer = _FakeIndexer(ids=["c1"])
    reconciler = IndexReconciler(_container(indexer, _RetrieverWithoutListIds(), ledger))

    report = reconciler.check()

    assert report.divergences[0].missing_in_lexical == ["c1"]


def test_repair_removes_orphans_from_both_stores() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1"])
    indexer = _FakeIndexer(ids=["c1", "orphan-vector"])
    retriever = _FakeRetriever(ids=["c1", "orphan-lexical"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))
    report = reconciler.check()

    result = reconciler.repair(report)

    assert result.removed_orphans_in_vector == ["orphan-vector"]
    assert result.removed_orphans_in_lexical == ["orphan-lexical"]
    assert "orphan-vector" not in indexer.list_ids()
    assert "orphan-lexical" not in retriever.list_ids()


def test_repair_does_not_invent_content_for_missing_chunks() -> None:
    """The core honesty property of this job: repair never fabricates a
    missing chunk's content — it reports it as unresolved instead."""
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1", "c2"])
    indexer = _FakeIndexer(ids=["c1"])  # c2 genuinely missing everywhere
    retriever = _FakeRetriever(ids=["c1"])
    reconciler = IndexReconciler(_container(indexer, retriever, ledger))
    report = reconciler.check()

    result = reconciler.repair(report)

    assert result.removed_orphans_in_vector == []
    assert len(result.unresolved_missing) == 1
    assert result.unresolved_missing[0].document_key == "doc-1"
    assert "c2" not in indexer.list_ids()  # not fabricated


def test_repair_skips_lexical_deletion_when_retriever_cannot_delete() -> None:
    ledger = InMemoryLifecycleLedger()
    ledger.record_ingested("doc-1", "acme-corp", "hash-a", ["c1"])
    indexer = _FakeIndexer(ids=["c1", "orphan-vector"])
    reconciler = IndexReconciler(_container(indexer, _RetrieverWithoutListIds(), ledger))
    report = reconciler.check()

    result = reconciler.repair(report)

    assert result.removed_orphans_in_vector == ["orphan-vector"]
    assert result.removed_orphans_in_lexical == []
