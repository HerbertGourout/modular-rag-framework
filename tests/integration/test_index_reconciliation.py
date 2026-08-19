"""Integration tests for orchestration.reconciliation.IndexReconciler against a
real Qdrant store — requires Qdrant on localhost:6333 (same convention as
test_qdrant_store.py). Not run by default — deselect with `-m "not integration"`.

`tests/unit/orchestration/test_reconciliation.py` already covers `check()`/
`repair()`'s logic against fake indexer/retriever/ledger doubles; what those
cannot prove is that the real `QdrantStore.list_ids()`/`delete()` calls this
class makes actually behave the way the fakes assume against a real server
(pagination, real id round-tripping, a real delete actually removing points).

This file's own lexical/BM25 side is a controlled fake, not a real backend —
proving lexical reconciliation would need a real `BM25Retriever`/lexical
index, which is out of this file's scope (it exists to prove the real Qdrant
surface). `_MatchingLexicalRetriever` (below) is deliberately NOT the bare
`object()` an earlier version of this file used: `Container.retriever` raises
`RegistryError` for an unregistered role (confirmed by reading
`orchestration/container.py`'s property implementations — unlike `reranker`/
`guard`/`lifecycle_ledger`, which return `None` via `.get()`), so *some*
double must be registered; but `IndexReconciler._list_lexical_ids()` degrades
an absent `list_ids()` to an empty list, and `check()` then reports every
ledger-expected id as `missing_in_lexical` against that empty list — a real,
if unintended, lexical divergence this file's vector-only scope was never
meant to introduce (Codex review HIGH-001, round 2, reproduced directly:
registering a bare `object()` made even the "no divergence" test report a
`missing_in_lexical` divergence for every expected id). `_MatchingLexicalRetriever`
instead always reports exactly the ids each test explicitly configures as
"present," which each test sets to match whatever it wants the *lexical* side
to honestly, uneventfully agree with — isolating every assertion to the real
Qdrant (vector) behavior under test, without silently faking lexical
correctness by skipping the check IndexReconciler actually performs.

Batch 10 (external plan; not this repo's own docs/refactoring-plan.md Lot/Lot
sequence) — the "migration and renovation test" the task named alongside
requirements-lock.txt-style CI wiring for tests/integration/test_postgres_migrations.py.
"Renovation" most plausibly reads as "reconciliation" (id-presence divergence
detection/repair against a real store) rather than "renovation" in its literal
sense — this file exists for that reading; see .review/handoff.md for the
alternate reading this task's own phrasing leaves open.
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.ingestion.lifecycle.in_memory_ledger import InMemoryLifecycleLedger
from modular_rag.orchestration.container import Container
from modular_rag.orchestration.reconciliation import IndexReconciler

COLLECTION = "test_index_reconciliation"
DIM = 4


class _MatchingLexicalRetriever:
    """A `list_ids()`-only double for the `retriever` role. Each test sets
    `.ids` to whatever it wants the lexical side to honestly report as
    present, so `IndexReconciler.check()`'s lexical comparison always agrees
    with that test's own setup and never contributes a divergence the test
    isn't specifically asserting about."""

    def __init__(self) -> None:
        self.ids: list[str] = []

    def list_ids(self) -> list[str]:
        return list(self.ids)


def _chunk(content: str, embedding: list[float]) -> Chunk:
    c = Chunk(id=new_id(), doc_id="doc-1", content=content)
    c.embedding = embedding
    return c


@pytest.fixture()
def store():
    s = QdrantStore(url="http://localhost:6333", collection=COLLECTION, vector_size=DIM)
    s.clear()
    yield s
    s.clear()


@pytest.fixture()
def reconciler(store):
    ledger = InMemoryLifecycleLedger()
    lexical = _MatchingLexicalRetriever()
    container = Container(manifest=None)  # type: ignore[arg-type]  # not used by IndexReconciler
    container.register("indexer", store)
    container.register("lifecycle_ledger", ledger)
    container.register("retriever", lexical)
    return IndexReconciler(container), store, ledger, lexical


@pytest.mark.integration
def test_check_reports_no_divergence_when_ledger_and_vector_store_agree(reconciler):
    reconciler_, store, ledger, lexical = reconciler
    chunks = [
        _chunk("RAG stands for Retrieval Augmented Generation", [1.0, 0.0, 0.0, 0.0]),
        _chunk("Paris is the capital of France", [0.0, 1.0, 0.0, 0.0]),
    ]
    store.index(chunks)
    ledger.record_ingested("doc-1", "tenant-a", "hash-a", [c.id for c in chunks])
    lexical.ids = [c.id for c in chunks]  # lexical side agrees too -- no divergence anywhere

    report = reconciler_.check()

    assert report.documents_checked == 1
    assert report.divergences == []
    assert report.orphaned_in_vector == []
    assert report.orphaned_in_lexical == []


@pytest.mark.integration
def test_check_detects_a_chunk_missing_from_the_vector_store(reconciler):
    """Simulates a crash between the ledger write and the vector write —
    the ledger believes a chunk id is indexed, but the store never actually
    received it. The lexical side is set to fully agree with the ledger, so
    the only divergence this test can observe is the vector-side one under
    test."""
    reconciler_, store, ledger, lexical = reconciler
    indexed_chunk = _chunk("RAG stands for Retrieval Augmented Generation", [1.0, 0.0, 0.0, 0.0])
    store.index([indexed_chunk])
    never_indexed_id = new_id()
    ledger.record_ingested("doc-1", "tenant-a", "hash-a", [indexed_chunk.id, never_indexed_id])
    lexical.ids = [indexed_chunk.id, never_indexed_id]

    report = reconciler_.check()

    assert len(report.divergences) == 1
    divergence = report.divergences[0]
    assert divergence.document_key == "doc-1"
    assert divergence.missing_in_vector == [never_indexed_id]
    assert divergence.missing_in_lexical == []


@pytest.mark.integration
def test_check_detects_an_orphaned_vector_not_tracked_by_any_active_document(reconciler):
    """A chunk present in the store that no active ledger record claims —
    e.g. a document deleted from the ledger without its vectors being
    cleaned up. Lexical is set to match the ledger's own expectation exactly,
    so only the vector-side orphan under test shows up."""
    reconciler_, store, ledger, lexical = reconciler
    tracked_chunk = _chunk("Paris is the capital of France", [0.0, 1.0, 0.0, 0.0])
    orphan_chunk = _chunk("Untracked orphan content", [0.0, 0.0, 1.0, 0.0])
    store.index([tracked_chunk, orphan_chunk])
    ledger.record_ingested("doc-1", "tenant-a", "hash-a", [tracked_chunk.id])
    lexical.ids = [tracked_chunk.id]

    report = reconciler_.check()

    assert report.divergences == []
    assert report.orphaned_in_vector == [orphan_chunk.id]
    assert report.orphaned_in_lexical == []


@pytest.mark.integration
def test_repair_deletes_orphaned_vectors_and_leaves_missing_unresolved(reconciler):
    reconciler_, store, ledger, lexical = reconciler
    tracked_chunk = _chunk("Paris is the capital of France", [0.0, 1.0, 0.0, 0.0])
    orphan_chunk = _chunk("Untracked orphan content", [0.0, 0.0, 1.0, 0.0])
    store.index([tracked_chunk, orphan_chunk])
    never_indexed_id = new_id()
    ledger.record_ingested(
        "doc-1", "tenant-a", "hash-a", [tracked_chunk.id, never_indexed_id]
    )
    lexical.ids = [tracked_chunk.id, never_indexed_id]

    report = reconciler_.check()
    result = reconciler_.repair(report)

    assert result.removed_orphans_in_vector == [orphan_chunk.id]
    assert len(result.unresolved_missing) == 1
    assert result.unresolved_missing[0].missing_in_vector == [never_indexed_id]
    assert result.unresolved_missing[0].missing_in_lexical == []

    remaining_ids = set(store.list_ids())
    assert orphan_chunk.id not in remaining_ids
    assert tracked_chunk.id in remaining_ids
