"""Integration tests for QdrantStore — requires Qdrant on localhost:6333."""
import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk

COLLECTION = "test_qdrant_store"
DIM = 4  # tiny vectors for fast tests


@pytest.fixture()
def store():
    s = QdrantStore(url="http://localhost:6333", collection=COLLECTION, vector_size=DIM)
    s.clear()
    yield s
    s.clear()


def _chunk(content: str, embedding: list[float]) -> Chunk:
    c = Chunk(id=new_id(), doc_id="doc-1", content=content)
    c.embedding = embedding
    return c


@pytest.mark.integration
def test_index_and_retrieve_by_vector(store):
    chunks = [
        _chunk("RAG stands for Retrieval Augmented Generation", [1.0, 0.0, 0.0, 0.0]),
        _chunk("Paris is the capital of France", [0.0, 1.0, 0.0, 0.0]),
        _chunk("Python is a programming language", [0.0, 0.0, 1.0, 0.0]),
    ]
    indexed = store.index(chunks)
    assert indexed == 3

    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=1)
    assert len(results) == 1
    assert "RAG" in results[0].chunk.content
    assert results[0].score > 0.9
    assert results[0].rank == 1


@pytest.mark.integration
def test_retrieve_top_k(store):
    chunks = [_chunk(f"document {i}", [float(i == j) for j in range(DIM)]) for i in range(DIM)]
    store.index(chunks)
    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=2)
    assert len(results) == 2
    assert results[0].rank == 1
    assert results[1].rank == 2


@pytest.mark.integration
def test_delete(store):
    chunk = _chunk("to be deleted", [1.0, 0.0, 0.0, 0.0])
    store.index([chunk])
    store.delete([chunk.id])
    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=10)
    ids = [r.chunk.id for r in results]
    assert chunk.id not in ids


@pytest.mark.integration
def test_clear(store):
    store.index([_chunk("something", [1.0, 0.0, 0.0, 0.0])])
    store.clear()
    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=10)
    assert results == []
