"""Contract conformance tests for Indexer / VectorIndexer implementations.

QdrantStore's constructor is network-free (`_get_client()`/`_ensure_collection()`
are lazy, only fired by a real `index()`/`delete()`/`clear()`/`retrieve_by_vector()`
call), so Protocol conformance and `ensure_vector_size()` — a pure in-memory
reconciliation, per contracts/indexing.py's VectorIndexer docstring — are both
testable here without a live Qdrant. `index()`/`delete()`/`clear()`/`list_ids()`
behaviour needs a live store and is covered by tests/integration/test_qdrant_store.py
instead, matching the existing VectorRetriever/HybridRetriever exclusion in
.claude/rules/tests.md.

The pure structural checks below (isinstance, name()) share module-level instances,
matching the convention in the other tests/contract/test_*_conformance.py files.
`ensure_vector_size()` *mutates* instance state, so — unlike the other conformance
files, none of whose Protocol methods mutate the object under test — those tests
each construct their own fresh `QdrantStore()` instead of reusing a shared instance,
to stay order-independent (test-specialist review: a shared instance made
`test_ensure_vector_size_derives_when_not_explicitly_configured` silently depend on
running before any other test that also called `ensure_vector_size` on it).
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.contracts.indexing import Indexer, VectorIndexer
from modular_rag.core.errors import ConfigurationError

INDEXERS = [QdrantStore()]
VECTOR_INDEXERS = [QdrantStore()]


@pytest.mark.parametrize("indexer", INDEXERS, ids=lambda i: type(i).__name__)
def test_implements_indexer_protocol(indexer):
    assert isinstance(indexer, Indexer)


@pytest.mark.parametrize("indexer", VECTOR_INDEXERS, ids=lambda i: type(i).__name__)
def test_implements_vector_indexer_protocol(indexer):
    assert isinstance(indexer, VectorIndexer)


@pytest.mark.parametrize("indexer", INDEXERS, ids=lambda i: type(i).__name__)
def test_name_returns_non_empty_string(indexer):
    assert isinstance(indexer.name(), str)
    assert len(indexer.name()) > 0


def test_bind_embedder_accepts_a_real_embedder_without_reading_its_dimensions():
    """`bind_embedder()` (ADR-0009's public VectorIndexer method, replacing
    an earlier private-attribute injection convention — Codex review, second
    pass) must not itself trigger reconciliation; `QdrantStore` defers that
    to `_get_client()`."""
    from modular_rag.adapters.embeddings.openai_embedder import OpenAIEmbedder

    indexer = QdrantStore()
    embedder = OpenAIEmbedder()

    indexer.bind_embedder(embedder)  # must not raise or touch the network

    assert indexer.vector_size == 384  # unreconciled until _get_client() runs


def test_ensure_vector_size_derives_when_not_explicitly_configured():
    indexer = QdrantStore()

    indexer.ensure_vector_size(768)

    assert indexer.vector_size == 768


def test_ensure_vector_size_raises_on_explicit_mismatch():
    indexer = QdrantStore(vector_size=384)

    with pytest.raises(ConfigurationError):
        indexer.ensure_vector_size(768)


def test_ensure_vector_size_is_last_call_wins_when_never_explicitly_configured():
    """Pins current behaviour (test-specialist review): with no explicit
    `vector_size`, each call adopts its argument outright — there is no
    lock-after-first-derive. In the real pipeline (ADR-0009)
    `QdrantStore._get_client()` calls this at most once per
    freshly-constructed store, so this only matters for direct/test callers
    that reuse one instance."""
    indexer = QdrantStore()

    indexer.ensure_vector_size(768)
    indexer.ensure_vector_size(384)

    assert indexer.vector_size == 384
