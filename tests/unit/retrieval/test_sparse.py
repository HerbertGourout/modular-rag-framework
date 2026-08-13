"""Unit tests for retrieval/retrievers/sparse.py — PersistentSparseRetriever
(Lot 5, persistent sparse retrieval). Mirrors test_vector.py's pattern of
injecting a fake `_sparse_store` to prove delegation and tenant_id pass-through,
without needing a live Qdrant.
"""
from __future__ import annotations

import pytest

from modular_rag.core.errors import RetrievalError
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever


class _RecordingStore:
    def __init__(self) -> None:
        self.last_search_call: dict | None = None
        self.indexed: list[Chunk] = []
        self.deleted: list[str] = []
        self.cleared = False
        self.closed = False

    def retrieve_by_text(self, query_text: str, k: int = 10, tenant_id: str | None = None):  # type: ignore[no-untyped-def]
        self.last_search_call = {"query_text": query_text, "k": k, "tenant_id": tenant_id}
        return []

    def index(self, chunks: list[Chunk]) -> int:
        self.indexed.extend(chunks)
        return len(chunks)

    def delete(self, ids: list[str]) -> None:
        self.deleted = ids

    def clear(self) -> None:
        self.cleared = True

    def list_ids(self) -> list[str]:
        return [c.id for c in self.indexed]

    def close(self) -> None:
        self.closed = True


def test_name_is_sparse_qdrant():
    assert PersistentSparseRetriever().name() == "sparse-qdrant"


def test_retrieve_raises_when_no_store_was_ever_injected():
    """Constructing PersistentSparseRetriever() with no `store=` is
    deliberately network-free (mirrors VectorRetriever's unwired-_store
    case) — but using it before app/default_factories.py injects a real
    QdrantSparseStore must fail loudly, not silently return nothing."""
    with pytest.raises(RetrievalError, match="QdrantSparseStore"):
        PersistentSparseRetriever().retrieve(Query(text="hello"))


def test_index_raises_when_no_store_was_ever_injected():
    with pytest.raises(RetrievalError, match="QdrantSparseStore"):
        PersistentSparseRetriever().index([Chunk(doc_id=new_id(), content="hello")])


def test_retrieve_passes_the_query_text_and_tenant_id_to_the_store():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store

    retriever.retrieve(Query(text="hello whales", tenant_id="acme-corp"), k=5)

    assert store.last_search_call == {
        "query_text": "hello whales",
        "k": 5,
        "tenant_id": "acme-corp",
    }


def test_retrieve_passes_none_tenant_id_when_query_has_none():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store

    retriever.retrieve(Query(text="hello"), k=5)

    assert store.last_search_call["tenant_id"] is None


def test_index_delegates_to_the_store():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store
    chunk = Chunk(doc_id=new_id(), content="hello world")

    n = retriever.index([chunk])

    assert n == 1
    assert chunk in store.indexed


def test_delete_delegates_to_the_store():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store

    retriever.delete(["a", "b"])

    assert store.deleted == ["a", "b"]


def test_clear_delegates_to_the_store():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store

    retriever.clear()

    assert store.cleared is True


def test_list_ids_delegates_to_the_store():
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store
    chunk = Chunk(doc_id=new_id(), content="hello world")
    store.indexed.append(chunk)

    assert retriever.list_ids() == [chunk.id]


def test_close_delegates_to_the_store():
    """Codex review (Lot 5, MED-001): Container.close() only reaches
    directly-registered components — before this fix, PersistentSparseRetriever
    had no close() at all, so a standalone `retriever.type: sparse-qdrant`
    wiring leaked its QdrantSparseStore's client on shutdown."""
    store = _RecordingStore()
    retriever = PersistentSparseRetriever()
    retriever._sparse_store = store

    retriever.close()

    assert store.closed is True


def test_close_is_a_no_op_when_no_store_was_ever_injected():
    PersistentSparseRetriever().close()  # must not raise
