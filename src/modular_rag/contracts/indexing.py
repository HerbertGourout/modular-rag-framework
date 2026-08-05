from __future__ import annotations

from typing import Protocol, runtime_checkable

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
