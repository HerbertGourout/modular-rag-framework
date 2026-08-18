"""Persistent sparse (lexical) retrieval — the durable-deployment
alternative to `retrieval.retrievers.bm25.BM25Retriever` (Lot 5 — persistent
sparse retrieval). `BM25Retriever` stays the explicit, in-memory,
development-only lexical adapter (see its own docstring); this class is what
`HybridRetriever`'s injected lexical backend becomes for a manifest that
needs the lexical index to survive a restart and stay consistent across
replicas — both are properties of Qdrant itself, not of any code here.

Implements both `Indexer` and `Retriever` — same double-conformance shape as
`BM25Retriever` — by delegating to an injected store satisfying the local
`_SparseStore` Protocol below.

Deliberately does *not* import `adapters.vectorstores.qdrant_sparse_store`
directly: `scripts/check_layering.py` forbids a domain module (`retrieval/`)
from importing `adapters/` (CLAUDE.md §02 — "domain modules import only
contracts/ + core/models/"). Same pattern as `retrieval.retrievers.vector.
VectorRetriever`'s locally-defined `_VectorStore` Protocol + `_store`
attribute — but with a *different* attribute name (`_sparse_store`, not
`_store`): architecture-reviewer finding (Lot 5) — `orchestration/registry.py`'s
post-wiring step probes `hasattr(target, "_store")` on `container.retriever`
itself as a *global*, name-based convention (not one scoped to
`VectorRetriever` specifically). When this class is wired standalone as
`retriever.type: "sparse-qdrant"`, an attribute literally named `_store`
would be silently overwritten with `container.indexer` (the *dense*
`QdrantStore`) right after construction, discarding the real
`QdrantSparseStore` injected by `app/default_factories.py` — confirmed by
wiring a real manifest and inspecting the result. Naming it `_sparse_store`
sidesteps that collision entirely; `orchestration/registry.py` needed no
change since its convention is deliberately narrow (only ever reads
`_embedder`/`_store`).
"""
from __future__ import annotations

from typing import Protocol

from modular_rag.core.errors import RetrievalError
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class _SparseStore(Protocol):
    def index(self, chunks: list[Chunk]) -> int: ...

    def delete(self, ids: list[str]) -> None: ...

    def clear(self) -> None: ...

    def list_ids(self) -> list[str]: ...

    def retrieve_by_text(
        self, query_text: str, k: int = 10, tenant_id: str | None = None
    ) -> list[RetrievedChunk]: ...

    def close(self) -> None: ...

    def check_health(self) -> list[DependencyHealth]: ...


class PersistentSparseRetriever:
    def __init__(self, store: _SparseStore | None = None) -> None:
        self._sparse_store = store  # injected by app/default_factories.py

    def name(self) -> str:
        return "sparse-qdrant"

    def _get_store(self) -> _SparseStore:
        if self._sparse_store is None:
            raise RetrievalError(
                "PersistentSparseRetriever requires a QdrantSparseStore — wire one via "
                "app/default_factories.py's 'sparse-qdrant' factory."
            )
        return self._sparse_store

    def index(self, chunks: list[Chunk]) -> int:
        return self._get_store().index(chunks)

    def delete(self, ids: list[str]) -> None:
        self._get_store().delete(ids)

    def clear(self) -> None:
        self._get_store().clear()

    def list_ids(self) -> list[str]:
        return self._get_store().list_ids()

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        # tenant_id passed through for query-time filtering — same pattern
        # as VectorRetriever.retrieve() (Lot 12b); TenantIsolationPolicy.
        # filter_chunks() remains the fail-closed backstop regardless.
        return self._get_store().retrieve_by_text(query.text, k=k, tenant_id=query.tenant_id)

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)

    def close(self) -> None:
        """Codex review (Lot 5, MED-001): `Container.close()` only reaches
        directly-registered components (`getattr(component, "close", None)`
        over `Container._store`'s values) — when this class is wired
        standalone as `retriever.type: "sparse-qdrant"`, the owned
        `QdrantSparseStore`'s client was never closed, since
        `PersistentSparseRetriever` itself had no `close()` at all. No-op
        (not an error) when never wired, matching `QdrantSparseStore.close()`'s
        own idempotent behavior."""
        if self._sparse_store is not None:
            self._sparse_store.close()

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). Delegates to the injected store; `[]` (nothing to
        report) when unwired — matching `close()`'s "no-op when unwired"
        precedent above rather than fabricating a health verdict for a
        wiring state that would already fail loudly (`RetrievalError`) on
        any real `retrieve()`/`index()` call."""
        if self._sparse_store is None:
            return []
        return self._sparse_store.check_health()
