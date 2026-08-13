"""Unit tests for app/default_factories.py's non-trivial factory functions
(Lot 5, persistent sparse retrieval): resolving a manifest's `retriever.config.
lexical` ("bm25-memory" | "sparse-qdrant") into a concrete lexical-backend
object before constructing `HybridRetriever`. This construction has to live
here (the unrestricted top-level `app/` layer) rather than inside
`HybridRetriever` itself, which lives in `retrieval/` and cannot import
`adapters.vectorstores.qdrant_sparse_store` directly
(`scripts/check_layering.py`).
"""
from __future__ import annotations

import pytest

from modular_rag.app.default_factories import (
    _build_hybrid_retriever,
    _build_sparse_qdrant_retriever,
    create_default_registry,
)
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import ConfigurationError
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever
from modular_rag.retrieval.retrievers.sparse import PersistentSparseRetriever


def test_hybrid_defaults_to_bm25_memory_when_lexical_is_omitted():
    retriever = _build_hybrid_retriever(ComponentConfig(type="hybrid", config={}))

    assert isinstance(retriever._lexical, BM25Retriever)


def test_hybrid_lexical_bm25_memory_is_explicit_too():
    retriever = _build_hybrid_retriever(
        ComponentConfig(type="hybrid", config={"lexical": "bm25-memory"})
    )

    assert isinstance(retriever._lexical, BM25Retriever)


def test_hybrid_lexical_sparse_qdrant_selects_persistent_sparse_retriever():
    retriever = _build_hybrid_retriever(
        ComponentConfig(type="hybrid", config={"lexical": "sparse-qdrant", "collection": "docs"})
    )

    assert isinstance(retriever._lexical, PersistentSparseRetriever)


def test_hybrid_lexical_sparse_qdrant_derives_its_collection_name_when_not_given():
    retriever = _build_hybrid_retriever(
        ComponentConfig(type="hybrid", config={"lexical": "sparse-qdrant", "collection": "docs"})
    )

    assert retriever._lexical._sparse_store._collection == "docs_sparse"


def test_hybrid_lexical_sparse_qdrant_honors_an_explicit_sparse_collection():
    retriever = _build_hybrid_retriever(
        ComponentConfig(
            type="hybrid",
            config={
                "lexical": "sparse-qdrant",
                "collection": "docs",
                "sparse_collection": "custom_sparse",
            },
        )
    )

    assert retriever._lexical._sparse_store._collection == "custom_sparse"


def test_hybrid_lexical_sparse_qdrant_propagates_url_and_api_key():
    """architecture-reviewer finding (Lot 5): the first version of this
    factory silently dropped `url`/`api_key` for the sparse leg whenever a
    manifest didn't separately duplicate them under `retriever.config` —
    `secure-enterprise-rag.yaml` originally only set them under
    `indexer.config`, so the sparse leg pointed at localhost with no
    credentials regardless of the preset's real Qdrant endpoint."""
    retriever = _build_hybrid_retriever(
        ComponentConfig(
            type="hybrid",
            config={
                "lexical": "sparse-qdrant",
                "collection": "docs",
                "url": "https://qdrant.prod:6333",
                "api_key": "prod-key",
            },
        )
    )

    assert retriever._lexical._sparse_store._url == "https://qdrant.prod:6333"
    assert retriever._lexical._sparse_store._api_key == "prod-key"


def test_hybrid_lexical_and_sparse_collection_are_not_forwarded_to_hybridretriever_init():
    """Both keys are consumed here, not passed through as unexpected
    HybridRetriever constructor kwargs (which would raise TypeError)."""
    retriever = _build_hybrid_retriever(
        ComponentConfig(
            type="hybrid",
            config={"lexical": "sparse-qdrant", "collection": "docs", "vector_weight": 0.6},
        )
    )

    assert retriever.vector_weight == 0.6


def test_hybrid_lexical_sparse_qdrant_forwards_tuning_params_to_the_store_not_hybridretriever():
    """Codex review (Lot 5, MED-002): `avgdl`/`k1`/`b`/`timeout` are
    QdrantSparseStore-only constructor parameters — HybridRetriever.__init__
    does not accept any of them. Reproduced before this fix: setting
    `avgdl` under `retriever.config` alongside `lexical: sparse-qdrant`
    raised `TypeError: HybridRetriever.__init__() got an unexpected keyword
    argument 'avgdl'`."""
    retriever = _build_hybrid_retriever(
        ComponentConfig(
            type="hybrid",
            config={
                "lexical": "sparse-qdrant",
                "collection": "docs",
                "timeout": 5.0,
                "avgdl": 256.0,
                "k1": 2.0,
                "b": 0.5,
            },
        )
    )

    store = retriever._lexical._sparse_store
    assert store._timeout == 5.0
    assert store._avgdl == 256.0
    assert store._k1 == 2.0
    assert store._b == 0.5


def test_hybrid_sparse_tuning_params_are_popped_even_when_bm25_memory_is_selected():
    """These four keys must never reach HybridRetriever's constructor,
    regardless of which lexical backend ends up selected — a manifest
    author leaving stray sparse-only keys under a bm25-memory config must
    not crash wiring either."""
    retriever = _build_hybrid_retriever(
        ComponentConfig(
            type="hybrid",
            config={"avgdl": 256.0, "k1": 2.0, "b": 0.5, "timeout": 5.0},
        )
    )

    assert isinstance(retriever._lexical, BM25Retriever)


def test_hybrid_lexical_sparse_qdrant_omits_unset_tuning_params_so_store_defaults_apply():
    """When not explicitly set, QdrantSparseStore's own constructor
    defaults must be what's actually used — not a duplicated/hardcoded
    value in the factory that could silently drift from them."""
    from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore

    retriever = _build_hybrid_retriever(
        ComponentConfig(type="hybrid", config={"lexical": "sparse-qdrant", "collection": "docs"})
    )

    default_store = QdrantSparseStore()
    store = retriever._lexical._sparse_store
    assert store._avgdl == default_store._avgdl
    assert store._k1 == default_store._k1
    assert store._b == default_store._b
    assert store._timeout == default_store._timeout


def test_hybrid_unknown_lexical_backend_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="unknown-backend"):
        _build_hybrid_retriever(
            ComponentConfig(type="hybrid", config={"lexical": "unknown-backend"})
        )


def test_standalone_sparse_qdrant_retriever_wires_a_real_store():
    retriever = _build_sparse_qdrant_retriever(
        ComponentConfig(type="sparse-qdrant", config={"collection": "docs_sparse"})
    )

    assert isinstance(retriever, PersistentSparseRetriever)
    assert retriever._sparse_store._collection == "docs_sparse"


def test_standalone_sparse_qdrant_retriever_survives_registry_wire_alongside_a_qdrant_indexer():
    """Regression test for the bug architecture-reviewer found and confirmed
    live (Lot 5): `orchestration/registry.py`'s post-wiring step blindly
    overwrites *any* `container.retriever` attribute named `_store` with
    `container.indexer` — `PersistentSparseRetriever` originally named its
    injected store `_store` (mirroring VectorRetriever), so wiring
    `retriever.type: sparse-qdrant` alongside any `indexer:` (the normal
    case — `indexer` is a required manifest field) silently replaced the
    real `QdrantSparseStore` with the *dense* `QdrantStore`, breaking every
    method (`retrieve_by_text` doesn't exist on `QdrantStore`). Renamed to
    `_sparse_store` to not collide with that convention — this test wires a
    *real* ComponentRegistry (not a hand-built factory call) to prove the
    fix holds end to end, not just at the factory-function level.
    """
    registry = create_default_registry()
    manifest = PipelineManifest(
        id="test-pipeline",
        chunker=ComponentConfig(type="fixed"),
        embedder=ComponentConfig(type="deterministic"),
        indexer=ComponentConfig(type="qdrant", config={"collection": "dense_docs"}),
        retriever=ComponentConfig(type="sparse-qdrant", config={"collection": "sparse_docs"}),
        generator=ComponentConfig(type="deterministic"),
    )

    container = registry.wire(manifest)

    assert isinstance(container.retriever, PersistentSparseRetriever)
    store = container.retriever._sparse_store
    assert store is not None
    assert store is not container.indexer  # not clobbered by post-wiring injection
    assert store._collection == "sparse_docs"
    assert hasattr(store, "retrieve_by_text")
