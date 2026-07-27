"""Qdrant vector store adapter — implements the Indexer and Retriever contracts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk

if TYPE_CHECKING:
    pass


class QdrantStore:
    """Wraps qdrant-client to provide Indexer + Retriever behaviour.

    Wire embedder separately: QdrantStore does not embed — the ingestion
    pipeline must supply pre-computed embeddings on each Chunk.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "mrag_default",
        vector_size: int = 384,
        api_key: str | None = None,
    ) -> None:
        self._url = url
        self._collection = collection
        self._vector_size = vector_size
        self._api_key = api_key
        self._client = None  # lazy

    def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise ImportError(
                    "qdrant-client is required for QdrantStore. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc

            self._client = QdrantClient(url=self._url, api_key=self._api_key)
            self._ensure_collection()
        return self._client

    def _ensure_collection(self) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        client = self._client
        existing = [c.name for c in client.get_collections().collections]
        if self._collection not in existing:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._vector_size, distance=Distance.COSINE),
            )

    # ------------------------------------------------------------------
    # Indexer contract
    # ------------------------------------------------------------------

    def index(self, chunks: list[Chunk]) -> int:
        from qdrant_client.http.models import PointStruct

        client = self._get_client()
        points = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(
                    f"Chunk {chunk.id} has no embedding. Embed before indexing."
                )
            points.append(
                PointStruct(
                    id=chunk.id,
                    vector=chunk.embedding,
                    payload={
                        "doc_id": chunk.doc_id,
                        "content": chunk.content,
                        "modality": chunk.modality,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "page": chunk.page,
                        **chunk.metadata,
                    },
                )
            )
        if points:
            client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def delete(self, chunk_ids: list[str]) -> None:
        from qdrant_client.http.models import PointIdsList

        client = self._get_client()
        client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=chunk_ids),
        )

    def clear(self) -> None:
        client = self._get_client()
        client.delete_collection(collection_name=self._collection)
        self._ensure_collection()

    def name(self) -> str:
        return "qdrant"

    # ------------------------------------------------------------------
    # Retriever contract
    # ------------------------------------------------------------------

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        raise NotImplementedError(
            "QdrantStore.retrieve() requires a query embedding. "
            "Use VectorRetriever wired with QdrantStore and an Embedder instead."
        )

    def retrieve_by_vector(self, vector: list[float], k: int = 10) -> list[RetrievedChunk]:
        """Retrieve chunks by a pre-computed query vector."""
        client = self._get_client()
        hits = client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=k,
        )
        results = []
        for rank, hit in enumerate(hits, 1):
            payload = hit.payload or {}
            chunk = Chunk(
                id=str(hit.id),
                doc_id=payload.get("doc_id", ""),
                content=payload.get("content", ""),
                start_char=payload.get("start_char"),
                end_char=payload.get("end_char"),
                page=payload.get("page"),
                metadata={k: v for k, v in payload.items() if k not in
                           {"doc_id", "content", "modality", "start_char", "end_char", "page"}},
            )
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=float(hit.score),
                    rank=rank,
                    retrieval_method=RetrievalMethod.VECTOR,
                )
            )
        return results
