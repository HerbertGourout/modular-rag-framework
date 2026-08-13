"""Unit tests for HybridRetriever's fusion-weight wiring and (Lot 5,
persistent sparse retrieval) injectable lexical backend.

Uses fake sub-retrievers injected on `_vector`/`_lexical` so the test exercises
HybridRetriever's own logic (weight pass-through to RRF, degraded-source
tracking, method tagging) without needing Qdrant. Resolving a manifest's
`lexical: "bm25-memory" | "sparse-qdrant"` string into a concrete object is
`app/default_factories.py`'s job (see tests/unit/app/test_default_factories.py)
— HybridRetriever itself only accepts an already-built `lexical_retriever`
(it lives in `retrieval/` and cannot import the Qdrant-backed adapter
directly, per `scripts/check_layering.py`).
"""
from __future__ import annotations

import pytest

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever
from modular_rag.retrieval.retrievers.hybrid import HybridRetriever


class _FakeRetriever:
    def __init__(self, hits: list[RetrievedChunk], name: str = "bm25") -> None:
        self._hits = hits
        self._name = name

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self._hits[:k]

    def name(self) -> str:
        return self._name


class _FailingRetriever:
    def name(self) -> str:
        return "bm25"

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        raise RuntimeError("source unavailable")


class _RecordingLexical:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.cleared = False
        self.indexed: list[Chunk] = []
        self.closed = False

    def name(self) -> str:
        return "bm25"

    def index(self, chunks: list[Chunk]) -> int:
        self.indexed.extend(chunks)
        return len(chunks)

    def delete(self, ids: list[str]) -> None:
        self.deleted = ids

    def close(self) -> None:
        self.closed = True

    def clear(self) -> None:
        self.cleared = True

    def list_ids(self) -> list[str]:
        return ["lexical-id-1", "lexical-id-2"]


def _hit(content: str, method: RetrievalMethod) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content)
    return RetrievedChunk(chunk=chunk, score=0.5, rank=1, retrieval_method=method)


def test_default_weights_favor_neither_source():
    retriever = HybridRetriever()
    vector_only = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([vector_only])
    retriever._lexical = _FakeRetriever([bm25_only])

    result = retriever.retrieve(Query(text="q"), k=10)

    ids = {r.chunk.id for r in result}
    assert ids == {vector_only.chunk.id, bm25_only.chunk.id}


def test_vector_weight_dominates_when_bm25_weight_is_zero():
    retriever = HybridRetriever(vector_weight=1.0, bm25_weight=0.0)
    vector_only = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([vector_only])
    retriever._lexical = _FakeRetriever([bm25_only])

    # Both tie at rank 1 in their own list; with bm25_weight=0 the vector-sourced
    # item must win the single top-1 slot.
    result = retriever.retrieve(Query(text="q"), k=1)

    assert [r.chunk.id for r in result] == [vector_only.chunk.id]


def test_higher_weight_wins_a_tie():
    retriever = HybridRetriever(vector_weight=0.9, bm25_weight=0.1)
    doc_a = _hit("doc a", RetrievalMethod.VECTOR)
    doc_b = _hit("doc b", RetrievalMethod.BM25)
    retriever._vector = _FakeRetriever([doc_a])
    retriever._lexical = _FakeRetriever([doc_b])

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result[0].chunk.id == doc_a.chunk.id


def test_hybrid_retriever_falls_back_when_vector_source_is_unavailable():
    retriever = HybridRetriever()
    bm25_only = _hit("bm25 document", RetrievalMethod.BM25)
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FakeRetriever([bm25_only])

    result = retriever.retrieve(Query(text="q"), k=10)

    assert [r.chunk.id for r in result] == [bm25_only.chunk.id]
    assert result[0].retrieval_method == RetrievalMethod.BM25


def test_hybrid_retriever_falls_back_when_lexical_source_is_unavailable():
    """test-specialist review (Lot 5): the mirror of
    test_hybrid_retriever_falls_back_when_vector_source_is_unavailable above
    was untested — lexical down, vector survives."""
    retriever = HybridRetriever()
    vector_only = _hit("vector document", RetrievalMethod.VECTOR)
    retriever._vector = _FakeRetriever([vector_only])
    retriever._lexical = _FailingRetriever()

    result = retriever.retrieve(Query(text="q"), k=10)

    assert [r.chunk.id for r in result] == [vector_only.chunk.id]
    assert result[0].retrieval_method == RetrievalMethod.VECTOR
    assert retriever.last_degraded_sources == ["lexical"]


def test_hybrid_retriever_returns_empty_list_when_both_sources_legitimately_find_nothing():
    """test-specialist review (Lot 5): every empty-result test elsewhere in
    this file uses *failing* retrievers — this is the other half of the
    "empty result vs. failure" distinction the Lot introduces: both sources
    succeed (no exception) but legitimately return zero hits. Must not be
    reported as a degraded source (that would be a false positive in the
    observability signal `RAGEngine` folds into the "retrieve" TraceStep)."""
    retriever = HybridRetriever()
    retriever._vector = _FakeRetriever([])
    retriever._lexical = _FakeRetriever([])

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result == []
    assert retriever.last_degraded_sources == []


def test_hybrid_retriever_returns_empty_list_without_raising_when_both_sources_fail():
    """Lot 4 (docs/refactoring-plan.md §2, 'Resilience'): `_safe_retrieve` catches
    *any* exception from either source and logs a warning, never re-raising. If
    both vector and lexical fail, `retrieve()` still returns `[]` — RAGEngine
    proceeds to generation with zero context — but (Lot 5) the failure is no
    longer indistinguishable from "no relevant documents exist": see
    `test_last_degraded_sources_*` below and `hybrid.retrieved.empty_due_to_failure`.
    """
    retriever = HybridRetriever()
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FailingRetriever()

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result == []


def test_delete_delegates_to_the_lexical_side_only():
    """Lot 12a (docs/refactoring-plan.md): the vector side is owned by
    Container.indexer separately; RAGEngine coordinates both."""
    retriever = HybridRetriever()
    lexical = _RecordingLexical()
    retriever._lexical = lexical

    retriever.delete(["chunk-1", "chunk-2"])

    assert lexical.deleted == ["chunk-1", "chunk-2"]


def test_clear_delegates_to_the_lexical_side_only():
    retriever = HybridRetriever()
    lexical = _RecordingLexical()
    retriever._lexical = lexical

    retriever.clear()

    assert lexical.cleared is True


def test_list_ids_delegates_to_the_lexical_side_only():
    retriever = HybridRetriever()
    retriever._lexical = _RecordingLexical()

    assert retriever.list_ids() == ["lexical-id-1", "lexical-id-2"]


def test_hybrid_retriever_mutates_rank_and_method_on_a_nominally_frozen_retrievedchunk():
    """`RetrievedChunk.model_config = {"frozen": True}` — normal attribute
    assignment (`chunk.rank = 5`) raises a pydantic ValidationError. HybridRetriever
    bypasses that via `object.__setattr__` to renumber rank/retrieval_method after
    fusion. This proves "frozen" is not actually enforced for chunks that pass
    through hybrid retrieval — a design quirk, not endorsed, characterized only.
    """
    retriever = HybridRetriever()
    vector_hit = _hit("vector document", RetrievalMethod.VECTOR)
    bm25_hit = _hit("bm25 document", RetrievalMethod.BM25)
    original_rank = vector_hit.rank
    retriever._vector = _FakeRetriever([vector_hit])
    retriever._lexical = _FakeRetriever([bm25_hit])

    with pytest.raises(Exception, match="frozen|immutable"):
        vector_hit.rank = 99  # sanity check: the model really is nominally frozen

    result = retriever.retrieve(Query(text="q"), k=10)

    # At least one fused result has been renumbered away from its pre-fusion rank
    # via object.__setattr__, despite the model's frozen config.
    assert any(r.rank != original_rank for r in result) or len(result) <= 1
    assert all(r.retrieval_method == RetrievalMethod.HYBRID for r in result)


# ---------------------------------------------------------------------------
# Lot 5 (persistent sparse retrieval) — injectable lexical backend.
# ---------------------------------------------------------------------------


def test_lexical_defaults_to_bm25_memory_when_no_retriever_is_injected():
    retriever = HybridRetriever()

    assert isinstance(retriever._lexical, BM25Retriever)


def test_lexical_uses_the_injected_retriever_when_given():
    fake = _RecordingLexical()

    retriever = HybridRetriever(lexical_retriever=fake)

    assert retriever._lexical is fake


def test_index_delegates_to_the_active_lexical_backend():
    """Closes the gap that previously forced RAGEngine.ingest_chunks() to
    reach into the private `_bm25` attribute directly — HybridRetriever had
    no index() at all before Lot 5."""
    retriever = HybridRetriever()
    lexical = _RecordingLexical()
    retriever._lexical = lexical
    chunk = Chunk(doc_id=new_id(), content="hello world")

    n = retriever.index([chunk])

    assert n == 1
    assert chunk in lexical.indexed


def test_lexical_only_results_are_tagged_with_the_active_backend_method():
    """Previously hardcoded RetrievalMethod.BM25 regardless of which lexical
    backend actually produced the results — mislabels sparse-qdrant-only
    results."""
    retriever = HybridRetriever()
    sparse_hit = _hit("sparse document", RetrievalMethod.SPARSE)
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FakeRetriever([sparse_hit], name="sparse-qdrant")

    result = retriever.retrieve(Query(text="q"), k=10)

    assert result[0].retrieval_method == RetrievalMethod.SPARSE


def test_close_delegates_to_the_lexical_backend_when_it_has_one():
    """Codex review (Lot 5, MED-001): Container.close() reaches
    Container.indexer directly (the dense/vector client), but the lexical
    leg's client (when it's a PersistentSparseRetriever wrapping a
    QdrantSparseStore) was previously unreachable — HybridRetriever had no
    close() at all."""
    retriever = HybridRetriever()
    lexical = _RecordingLexical()
    retriever._lexical = lexical

    retriever.close()

    assert lexical.closed is True


def test_close_is_a_no_op_when_the_lexical_backend_has_no_close():
    """BM25Retriever (the default lexical backend) owns no external
    resource and has no close() — getattr() must not raise."""
    HybridRetriever().close()  # must not raise


# ---------------------------------------------------------------------------
# Lot 5 — degraded-source observability. A genuine backend failure must be
# distinguishable (via `last_degraded_sources`) from a legitimate empty
# result, and surfaced for RAGEngine to fold into the "retrieve" TraceStep.
# ---------------------------------------------------------------------------


def test_last_degraded_sources_is_empty_when_both_sources_succeed():
    retriever = HybridRetriever()
    retriever._vector = _FakeRetriever([_hit("v", RetrievalMethod.VECTOR)])
    retriever._lexical = _FakeRetriever([_hit("l", RetrievalMethod.BM25)])

    retriever.retrieve(Query(text="q"), k=10)

    assert retriever.last_degraded_sources == []


def test_last_degraded_sources_names_the_failing_source():
    retriever = HybridRetriever()
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FakeRetriever([_hit("l", RetrievalMethod.BM25)])

    retriever.retrieve(Query(text="q"), k=10)

    assert retriever.last_degraded_sources == ["vector"]


def test_last_degraded_sources_names_both_sources_on_a_double_failure():
    retriever = HybridRetriever()
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FailingRetriever()

    retriever.retrieve(Query(text="q"), k=10)

    assert set(retriever.last_degraded_sources) == {"vector", "lexical"}


def test_last_degraded_sources_resets_on_each_retrieve_call():
    retriever = HybridRetriever()
    retriever._vector = _FailingRetriever()
    retriever._lexical = _FakeRetriever([_hit("l", RetrievalMethod.BM25)])
    retriever.retrieve(Query(text="q"), k=10)
    assert retriever.last_degraded_sources == ["vector"]

    retriever._vector = _FakeRetriever([_hit("v", RetrievalMethod.VECTOR)])
    retriever.retrieve(Query(text="q"), k=10)

    assert retriever.last_degraded_sources == []
