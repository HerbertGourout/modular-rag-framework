from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.contracts.embeddings import Embedder
from modular_rag.core.models.chunk import Chunk


@runtime_checkable
class Indexer(Protocol):
    """Write and delete Chunks in a persistent store (vector or lexical)."""

    def index(self, chunks: list[Chunk]) -> None: ...

    def delete(self, ids: list[str]) -> None: ...

    def clear(self) -> None: ...

    def list_ids(self) -> list[str]:
        """Enumerate every chunk id currently stored. Added in Lot 12b
        (docs/refactoring-plan.md) so `orchestration.reconciliation.IndexReconciler`
        can detect divergence between this index and the lexical retriever's
        own state, or the `LifecycleLedger`'s expected `chunk_ids`. Not
        conformance-tested here (no `Indexer` implementation besides
        `QdrantStore` exists, and it needs a live Qdrant — same exclusion as
        `VectorRetriever`/`HybridRetriever` in `.claude/rules/tests.md`);
        covered by `tests/integration/test_qdrant_store.py` instead.
        """
        ...

    def name(self) -> str: ...


@runtime_checkable
class VectorIndexer(Indexer, Protocol):
    """An `Indexer` backed by a dimension-sensitive vector store (e.g.
    Qdrant) — not every `Indexer` is one (a lexical/BM25-style store has no
    notion of vector dimension), so this stays a separate, narrower
    sub-protocol rather than a field added to `Indexer` itself.

    See ADR-0009 (docs/adr/0009-vector-indexer-dimension-reconciliation.md):
    `ComponentRegistry.wire()` calls `bind_embedder()` — a real, protocol-
    declared method, not a private-attribute convention orchestration merely
    hopes an implementation happens to read — to hand off the wired
    `Embedder`. What a `VectorIndexer` does with it is up to the
    implementation: call `ensure_vector_size(embedder.dimensions)`
    immediately inside `bind_embedder()`, or store the reference and defer
    until its own first real connection (`QdrantStore`'s choice, so a
    custom embedder whose `.dimensions` requires loading a real model is
    never forced to do so merely because a manifest was wired — see
    ADR-0009). Either way, a vector store's configured size is always
    derived from or validated against the embedder actually producing
    vectors for it before any collection is created or used — never a
    silent, possibly-wrong default. Deliberately methods, not properties:
    a data-only Protocol member makes `isinstance()` degrade to a plain
    `hasattr()` check, which would pass for a property with no setter and
    then raise `AttributeError` on assignment.
    """

    def bind_embedder(self, embedder: Embedder) -> None:
        """Receive the `Embedder` wired alongside this store in the same
        pipeline, so `ensure_vector_size(embedder.dimensions)` can be called
        — immediately, or lazily before this store's first real network use.
        Called exactly once, by `ComponentRegistry.wire()`, after both
        components are built."""
        ...

    def ensure_vector_size(self, dimensions: int) -> None:
        """Reconcile this store's configured vector size with `dimensions`
        (the bound `Embedder.dimensions`).

        If a vector size was explicitly configured (via the manifest's
        `indexer.config.vector_size`), raise `core.errors.ConfigurationError`
        on any mismatch — a manifest that declares one dimension while an
        embedder produces another is a configuration error, not something to
        silently paper over. If no size was explicitly configured, adopt
        `dimensions` as the value used the next time a collection needs to
        be created.
        """
        ...
