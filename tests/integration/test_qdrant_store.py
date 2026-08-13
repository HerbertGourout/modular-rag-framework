"""Integration tests for QdrantStore — requires Qdrant on localhost:6333."""
import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.core.errors import ConfigurationError
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


@pytest.mark.integration
def test_list_ids_returns_every_indexed_chunk_id(store):
    """Lot 12b (docs/refactoring-plan.md): added for
    orchestration.reconciliation.IndexReconciler to detect divergence."""
    chunks = [
        _chunk("first", [1.0, 0.0, 0.0, 0.0]),
        _chunk("second", [0.0, 1.0, 0.0, 0.0]),
    ]
    store.index(chunks)

    ids = store.list_ids()

    assert set(ids) == {c.id for c in chunks}


@pytest.mark.integration
def test_list_ids_reflects_deletion(store):
    chunk = _chunk("to be deleted", [1.0, 0.0, 0.0, 0.0])
    store.index([chunk])

    store.delete([chunk.id])

    assert chunk.id not in store.list_ids()


@pytest.mark.integration
def test_tenant_id_round_trips_through_index_and_retrieve(store):
    """Lot 12b: tenant_id used to be dropped on index and never reconstructed
    on retrieve, silently defeating Lot 11b's tenant-isolation filtering for
    the real Qdrant path."""
    chunk = Chunk(id=new_id(), doc_id="doc-1", content="tenant-scoped", tenant_id="acme-corp")
    chunk.embedding = [1.0, 0.0, 0.0, 0.0]
    store.index([chunk])

    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=1)

    assert results[0].chunk.tenant_id == "acme-corp"


@pytest.mark.integration
def test_index_does_not_let_metadata_override_the_real_tenant_id(store):
    """Codex review (Lot 5, HIGH-001): pre-existing bug in this store, found
    while writing the equivalent fix for the new QdrantSparseStore —
    `**chunk.metadata` was spread after the structured payload fields, so a
    caller-supplied metadata["tenant_id"] silently overrode the real,
    already-validated chunk.tenant_id."""
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="spoofed tenant",
        tenant_id="tenant-a",
        metadata={"tenant_id": "tenant-b"},
    )
    chunk.embedding = [1.0, 0.0, 0.0, 0.0]
    store.index([chunk])

    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=1)

    assert results[0].chunk.tenant_id == "tenant-a"
    assert store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=1, tenant_id="tenant-b") == []


@pytest.mark.integration
def test_retrieve_by_vector_with_tenant_id_excludes_other_tenants(store):
    """Lot 12b: query-time filtering follow-up to Lot 11b's tenant isolation
    — evaluated and implemented, not just left as an open question."""
    acme = Chunk(
        id=new_id(), doc_id="doc-1", content="acme content", tenant_id="acme-corp"
    )
    acme.embedding = [1.0, 0.0, 0.0, 0.0]
    other = Chunk(
        id=new_id(), doc_id="doc-2", content="other content", tenant_id="other-tenant"
    )
    other.embedding = [1.0, 0.0, 0.0, 0.0]
    store.index([acme, other])

    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=10, tenant_id="acme-corp")

    ids = {r.chunk.id for r in results}
    assert acme.id in ids
    assert other.id not in ids


@pytest.mark.integration
def test_ensure_collection_raises_on_dimension_mismatch_against_a_real_existing_collection():
    """The "already-existing collection" half of ADR-0009's dimension
    guarantee (docs/adr/0009-vector-indexer-dimension-reconciliation.md) —
    QdrantStore._ensure_collection() must reject a genuine mismatch against
    a real, already-created Qdrant collection, not just the hand-built fakes
    in tests/unit/adapters/vectorstores/test_qdrant_store.py (test-specialist
    review)."""
    collection = "test_qdrant_store_dim_mismatch"
    original = QdrantStore(url="http://localhost:6333", collection=collection, vector_size=4)
    original.clear()  # creates the collection at 4 dimensions
    try:
        mismatched = QdrantStore(url="http://localhost:6333", collection=collection, vector_size=8)
        with pytest.raises(ConfigurationError):
            mismatched.list_ids()
    finally:
        original.clear()


@pytest.mark.integration
def test_retrieve_by_vector_without_tenant_id_returns_all_tenants(store):
    """Backward-compatible default: omitting tenant_id applies no filter,
    matching pre-Lot-12b behavior exactly."""
    acme = Chunk(id=new_id(), doc_id="doc-1", content="acme content", tenant_id="acme-corp")
    acme.embedding = [1.0, 0.0, 0.0, 0.0]
    other = Chunk(id=new_id(), doc_id="doc-2", content="other content", tenant_id="other-tenant")
    other.embedding = [1.0, 0.0, 0.0, 0.0]
    store.index([acme, other])

    results = store.retrieve_by_vector([1.0, 0.0, 0.0, 0.0], k=10)

    ids = {r.chunk.id for r in results}
    assert acme.id in ids
    assert other.id in ids
