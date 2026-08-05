"""Unit tests for retrieval/retrievers/vector.py — VectorRetriever. No prior
direct unit coverage existed (only indirect, via test_hybrid.py's fakes).
Lot 12b, docs/refactoring-plan.md: proves `query.tenant_id` reaches the
underlying store's `retrieve_by_vector()` call, the query-time-filtering
follow-up to Lot 11b's tenant isolation.
"""
from __future__ import annotations

from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.vector import VectorRetriever


class _FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class _RecordingStore:
    def __init__(self) -> None:
        self.last_call: dict | None = None

    def retrieve_by_vector(self, vector, k: int = 10, tenant_id: str | None = None):  # type: ignore[no-untyped-def]
        self.last_call = {"vector": vector, "k": k, "tenant_id": tenant_id}
        return []


def test_retrieve_passes_the_query_tenant_id_to_the_store() -> None:
    store = _RecordingStore()
    retriever = VectorRetriever(embedder=_FakeEmbedder())
    retriever._store = store

    retriever.retrieve(Query(text="hello", tenant_id="acme-corp"), k=5)

    assert store.last_call["tenant_id"] == "acme-corp"
    assert store.last_call["k"] == 5


def test_retrieve_passes_none_tenant_id_when_query_has_none() -> None:
    store = _RecordingStore()
    retriever = VectorRetriever(embedder=_FakeEmbedder())
    retriever._store = store

    retriever.retrieve(Query(text="hello"), k=5)

    assert store.last_call["tenant_id"] is None
