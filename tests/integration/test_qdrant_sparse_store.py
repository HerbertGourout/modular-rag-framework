"""Integration tests for QdrantSparseStore — requires Qdrant on localhost:6333
(Lot 5, persistent sparse retrieval). Mirrors tests/integration/test_qdrant_store.py's
structure; the two acceptance-criteria tests at the bottom (restart persistence,
multi-instance consistency) are Lot 5-specific — proving the two properties an
in-memory BM25Retriever cannot offer.
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk

COLLECTION = "test_qdrant_sparse_store"


@pytest.fixture()
def store():
    s = QdrantSparseStore(url="http://localhost:6333", collection=COLLECTION)
    s.clear()
    yield s
    s.clear()


def _chunk(content: str, tenant_id: str | None = None) -> Chunk:
    return Chunk(id=new_id(), doc_id="doc-1", content=content, tenant_id=tenant_id)


@pytest.mark.integration
def test_index_and_retrieve_by_text(store):
    chunks = [
        _chunk("RAG stands for Retrieval Augmented Generation"),
        _chunk("Paris is the capital of France"),
        _chunk("Python is a programming language"),
    ]
    indexed = store.index(chunks)
    assert indexed == 3

    results = store.retrieve_by_text("Retrieval Augmented Generation", k=1)
    assert len(results) == 1
    assert "RAG" in results[0].chunk.content
    assert results[0].rank == 1


@pytest.mark.integration
def test_retrieve_by_text_finds_nothing_for_content_with_no_shared_terms(store):
    store.index([_chunk("Paris is the capital of France")])

    results = store.retrieve_by_text("completely unrelated whale biology", k=10)

    assert results == []


@pytest.mark.integration
def test_index_skips_content_with_no_word_tokens(store):
    """core.sparse_vectorizer.index_sparse_vector returns {} for degenerate
    content — an empty sparse vector cannot be upserted or searched."""
    n = store.index([_chunk("!!! ??? ...")])

    assert n == 0
    assert store.list_ids() == []


@pytest.mark.integration
def test_delete(store):
    chunk = _chunk("to be deleted")
    store.index([chunk])
    store.delete([chunk.id])

    results = store.retrieve_by_text("to be deleted", k=10)

    ids = [r.chunk.id for r in results]
    assert chunk.id not in ids


@pytest.mark.integration
def test_clear(store):
    store.index([_chunk("something searchable")])
    store.clear()

    results = store.retrieve_by_text("something searchable", k=10)

    assert results == []


@pytest.mark.integration
def test_list_ids_returns_every_indexed_chunk_id(store):
    chunks = [_chunk("first document"), _chunk("second document")]
    store.index(chunks)

    ids = store.list_ids()

    assert set(ids) == {c.id for c in chunks}


@pytest.mark.integration
def test_list_ids_reflects_deletion(store):
    chunk = _chunk("to be deleted")
    store.index([chunk])

    store.delete([chunk.id])

    assert chunk.id not in store.list_ids()


@pytest.mark.integration
def test_tenant_id_round_trips_through_index_and_retrieve(store):
    chunk = _chunk("tenant-scoped content", tenant_id="acme-corp")
    store.index([chunk])

    results = store.retrieve_by_text("tenant-scoped content", k=1)

    assert results[0].chunk.tenant_id == "acme-corp"


@pytest.mark.integration
def test_index_does_not_let_metadata_override_the_real_tenant_id(store):
    """Codex review (Lot 5, HIGH-001): reproduced against a real Qdrant
    server, not just the mocked unit test — a spoofed
    metadata={"tenant_id": ...} must never survive the round-trip."""
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world spoofed tenant",
        tenant_id="tenant-a",
        metadata={"tenant_id": "tenant-b"},
    )
    store.index([chunk])

    results = store.retrieve_by_text("hello world spoofed tenant", k=1)

    assert results[0].chunk.tenant_id == "tenant-a"
    # Also confirms the server-side tenant filter enforces the real value,
    # not the metadata-spoofed one.
    assert store.retrieve_by_text(
        "hello world spoofed tenant", k=1, tenant_id="tenant-b"
    ) == []


@pytest.mark.integration
def test_retrieve_by_text_with_tenant_id_excludes_other_tenants(store):
    """Backend-level tenant filtering (Lot 5, mirroring QdrantStore's
    retrieve_by_vector tenant_id filter, Lot 12b) — TenantIsolationPolicy.
    filter_chunks() remains the fail-closed backstop regardless."""
    acme = _chunk("acme shared content", tenant_id="acme-corp")
    other = _chunk("acme shared content", tenant_id="other-tenant")
    store.index([acme, other])

    results = store.retrieve_by_text("acme shared content", k=10, tenant_id="acme-corp")

    ids = {r.chunk.id for r in results}
    assert acme.id in ids
    assert other.id not in ids


@pytest.mark.integration
def test_retrieve_by_text_without_tenant_id_returns_all_tenants(store):
    acme = _chunk("shared content", tenant_id="acme-corp")
    other = _chunk("shared content", tenant_id="other-tenant")
    store.index([acme, other])

    results = store.retrieve_by_text("shared content", k=10)

    ids = {r.chunk.id for r in results}
    assert acme.id in ids
    assert other.id in ids


# ---------------------------------------------------------------------------
# Lot 5 acceptance criteria: "index lexical conservé après redémarrage" and
# "résultats cohérents entre réplicas" — see the test-specialist caveat on
# each test below for exactly what this environment can and cannot prove.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_a_fresh_store_instance_has_no_client_side_state_and_can_read_what_another_indexed():
    """test-specialist review (Lot 5): renamed from
    "...simulating_a_restart" — that name overclaimed. QdrantSparseStore
    holds no client-side corpus by construction (unlike BM25Retriever's
    in-memory `_chunks`), so "a fresh instance can read it" follows
    automatically the moment index()+retrieve_by_text() work at all — this
    test does not, and cannot, bounce the actual Qdrant server process, so
    it does NOT prove the "index lexical conservé après redémarrage"
    acceptance criterion by itself. A Qdrant instance with no persistent
    volume (e.g. `:memory:` mode, or a container with no volume mount)
    would pass this test and still lose everything on a real restart. What
    this test *does* prove, honestly: no per-process in-memory state exists
    to lose in the first place — the durability property then rests on
    Qdrant's own on-disk storage, which this suite cannot verify without an
    actual server bounce (out of scope for this Lot; flagged as a residual
    risk in the final report)."""
    collection = "test_qdrant_sparse_store_restart"
    writer = QdrantSparseStore(url="http://localhost:6333", collection=collection)
    writer.clear()
    try:
        writer.index([_chunk("citations survive a genuine restart")])

        reader = QdrantSparseStore(url="http://localhost:6333", collection=collection)
        results = reader.retrieve_by_text("citations survive a genuine restart", k=1)

        assert len(results) == 1
        assert "citations survive" in results[0].chunk.content
    finally:
        writer.clear()


@pytest.mark.integration
def test_two_independent_instances_return_the_same_correct_result_for_the_same_query():
    """test-specialist review (Lot 5): renamed from
    "...see_identical_results..." — two client connections to one
    single-node Qdrant instance are not two replicas; replication lag (what
    "cohérent entre réplicas" actually names) is neither exercised nor
    exercisable without a real multi-node cluster, out of scope for this
    Lot. What this test *does* prove: no per-connection client-side
    divergence for the same query against the same collection. Also closes
    a real gap flagged in review — the original version only asserted
    `ids_a == ids_b`, which would pass even if both connections agreed on
    the *wrong* answer (sparse scoring silently broken but deterministic);
    asserting the top hit is the actually-relevant document makes the test
    discriminating, not just self-consistent.
    """
    collection = "test_qdrant_sparse_store_multi_instance"
    writer = QdrantSparseStore(url="http://localhost:6333", collection=collection)
    writer.clear()
    try:
        relevant = _chunk("replica consistency across independent instances")
        irrelevant = _chunk("a second unrelated document about whales")
        writer.index([relevant, irrelevant])

        replica_a = QdrantSparseStore(url="http://localhost:6333", collection=collection)
        replica_b = QdrantSparseStore(url="http://localhost:6333", collection=collection)

        results_a = replica_a.retrieve_by_text("replica consistency", k=10)
        results_b = replica_b.retrieve_by_text("replica consistency", k=10)

        ids_a = [r.chunk.id for r in results_a]
        ids_b = [r.chunk.id for r in results_b]
        assert ids_a == ids_b
        assert ids_a[0] == relevant.id  # discriminating: not just self-consistent
    finally:
        writer.clear()
