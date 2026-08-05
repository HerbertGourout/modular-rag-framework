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
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._collection = collection
        self._vector_size = vector_size
        self._api_key = api_key
        self._timeout = timeout
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

            # QdrantClient's own timeout param is int-seconds only (unlike
            # openai/anthropic's float-seconds) — truncated here, not rounded,
            # so a sub-second value never silently becomes a *longer* timeout
            # than requested.
            self._client = QdrantClient(
                url=self._url, api_key=self._api_key, timeout=int(self._timeout)
            )
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
                        # tenant_id persisted explicitly (Lot 12b, docs/refactoring-plan.md):
                        # previously dropped here and never reconstructed in
                        # retrieve_by_vector(), which silently defeated Lot 11b's
                        # TenantIsolationPolicy.filter_chunks() for the real Qdrant
                        # path (every chunk round-tripped through Qdrant came back
                        # with tenant_id=None, indistinguishable from unclassified
                        # content — fail-closed filtering then dropped it either way,
                        # but for the wrong reason, and would incorrectly drop
                        # legitimately tenant-scoped content too).
                        "tenant_id": chunk.tenant_id,
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

    def list_ids(self) -> list[str]:
        """Enumerate every point id currently in the collection, via Qdrant's
        scroll API (no vectors/payload fetched — id listing only). Added in
        Lot 12b (docs/refactoring-plan.md) for `orchestration.reconciliation.IndexReconciler`
        to detect divergence against the lexical index / lifecycle ledger."""
        client = self._get_client()
        ids: list[str] = []
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=self._collection,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            ids.extend(str(p.id) for p in points)
            if offset is None:
                break
        return ids

    def name(self) -> str:
        return "qdrant"

    def close(self) -> None:
        """Release the underlying qdrant-client connection, if one was ever
        opened (Lot 14, docs/refactoring-plan.md — "own and close clients/
        resources"). A no-op when `_get_client()` was never called — closing
        a resource that was never opened is not an error."""
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Retriever contract
    # ------------------------------------------------------------------

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        raise NotImplementedError(
            "QdrantStore.retrieve() requires a query embedding. "
            "Use VectorRetriever wired with QdrantStore and an Embedder instead."
        )

    def retrieve_by_vector(
        self, vector: list[float], k: int = 10, tenant_id: str | None = None
    ) -> list[RetrievedChunk]:
        """Retrieve chunks by a pre-computed query vector.

        `tenant_id`, when given, applies a Qdrant payload filter so
        cross-tenant chunks are excluded *at query time* rather than fetched
        and discarded afterward (Lot 12b, docs/refactoring-plan.md —
        evaluating the query-time-partitioning follow-up flagged in Lot 11b:
        `security.policies.tenant_isolation.TenantIsolationPolicy.filter_chunks()`
        remains the fail-closed backstop regardless — this is a
        defense-in-depth/performance improvement on top of it, not a
        replacement for it).
        """
        client = self._get_client()
        query_filter = None
        if tenant_id is not None:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )
        hits = client.search(
            collection_name=self._collection,
            query_vector=vector,
            query_filter=query_filter,
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
                tenant_id=payload.get("tenant_id"),
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k
                    not in {
                        "doc_id",
                        "content",
                        "modality",
                        "start_char",
                        "end_char",
                        "page",
                        "tenant_id",
                    }
                },
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
