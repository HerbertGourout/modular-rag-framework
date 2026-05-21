from __future__ import annotations

import structlog

from modular_rag.core.enums import RetrievalMethod
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
        self._client: object | None = None

    def name(self) -> str:
        return "vector"

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from qdrant_client import QdrantClient

                self._client = QdrantClient(url=self.url, api_key=self.api_key or None)
            except ImportError as exc:
                raise ImportError("Install 'qdrant-client' (pip install modular-rag[v1]).") from exc
        return self._client

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        raise NotImplementedError(
            "VectorRetriever.retrieve — wire an Embedder and a Qdrant collection first."
        )

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
