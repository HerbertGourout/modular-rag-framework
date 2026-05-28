from __future__ import annotations

import structlog

from modular_rag.core.errors import RetrievalError
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk

log = structlog.get_logger(__name__)


class VectorRetriever:
    """Dense retrieval via a vector store (Qdrant by default)."""

    def __init__(
        self,
        collection: str = "documents",
        url: str = "http://localhost:6333",
        api_key: str = "",
        embedder: object | None = None,
    ) -> None:
        self.collection = collection
        self.url = url
        self.api_key = api_key
        self._embedder = embedder
        self._store: object | None = None  # injected by registry post-wiring

    def name(self) -> str:
        return "vector"

    def _get_store(self) -> object:
        """Return the QdrantStore, creating one lazily if not injected."""
        if self._store is None:
            from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
            self._store = QdrantStore(
                url=self.url,
                collection=self.collection,
                api_key=self.api_key or None,
            )
        return self._store

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        if self._embedder is None:
            raise RetrievalError(
                "VectorRetriever requires an embedder — wire one via the manifest embedder field."
            )
        query_vec: list[float] = self._embedder.embed([query.text])[0]  # type: ignore[union-attr]
        chunks = self._get_store().retrieve_by_vector(query_vec, k=k)  # type: ignore[union-attr]
        log.debug("vector.retrieved", chunks=len(chunks), query_id=query.id)
        return chunks

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
