"""Qdrant vector store adapter — implements the Indexer and Retriever contracts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk

if TYPE_CHECKING:
    from modular_rag.contracts.embeddings import Embedder

_DEFAULT_VECTOR_SIZE = 384


class QdrantStore:
    """Wraps qdrant-client to provide Indexer + Retriever behaviour.

    Wire embedder separately: QdrantStore does not embed — the ingestion
    pipeline must supply pre-computed embeddings on each Chunk.
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "mrag_default",
        vector_size: int | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._collection = collection
        # `vector_size=None` (ADR-0009) distinguishes "not given, derive from
        # the wired Embedder" from "explicitly set to exactly 384" — both
        # used to be indistinguishable once the constructor's own
        # `int = 384` default ran, which is what let a manifest silently get
        # a 384-dim collection regardless of its embedder's real output
        # size. `_get_client()` calls `ensure_vector_size()` once an
        # `_embedder` has been injected; direct/standalone construction
        # outside wiring keeps the 384 fallback so existing callers that
        # never touch dimension consistency are unaffected.
        self._vector_size = vector_size if vector_size is not None else _DEFAULT_VECTOR_SIZE
        self._vector_size_explicit = vector_size is not None
        self._api_key = api_key
        self._timeout = timeout
        self._client = None  # lazy
        # ADR-0009: bound by ComponentRegistry.wire() via `bind_embedder()`
        # (a real VectorIndexer protocol method, not a private-attribute
        # convention — Codex review, second pass) — kept unread until
        # `_get_client()` actually needs a live connection, so a custom
        # embedder whose `.dimensions` requires loading a real model is
        # never forced to do so merely because a manifest was wired
        # (CLAUDE.md §05.7).
        self._embedder: Embedder | None = None

    @property
    def vector_size(self) -> int:
        return self._vector_size

    def bind_embedder(self, embedder: Embedder) -> None:
        """Implements `contracts.indexing.VectorIndexer` (ADR-0009). Stores
        the reference; `_get_client()` calls `ensure_vector_size()` with it
        lazily, the first time a live connection is actually needed — see
        that method's docstring for why."""
        self._embedder = embedder

    def ensure_vector_size(self, dimensions: int) -> None:
        """Implements `contracts.indexing.VectorIndexer` (ADR-0009). Called by
        `_get_client()` — using the `Embedder` bound via `bind_embedder()` —
        the first time a live connection is actually needed, so this never
        runs merely because a manifest was wired. Still strictly before any
        network call itself (the "already-existing collection" half of the
        guarantee is `_ensure_collection()`'s job, right after)."""
        if self._vector_size_explicit:
            if self._vector_size != dimensions:
                raise ConfigurationError(
                    f"indexer.config.vector_size={self._vector_size} does not match this "
                    f"pipeline's embedder, which produces {dimensions}-dimensional vectors. "
                    "Fix indexer.config.vector_size to match, or remove it to derive "
                    "automatically from the embedder."
                )
        else:
            self._vector_size = dimensions

    def _get_client(self):
        if self._client is None:
            if self._embedder is not None:
                self.ensure_vector_size(self._embedder.dimensions)
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
            client = QdrantClient(
                url=self._url, api_key=self._api_key, timeout=int(self._timeout)
            )
            # Codex review (second pass, HIGH-002): `self._client` must not
            # be published until `_ensure_collection()` has actually passed
            # — assigning it first meant a caller that caught the
            # ConfigurationError from a dimension/named-vector mismatch and
            # retried would find `self._client` already non-None on the next
            # call, skip `_ensure_collection()` entirely (it only runs
            # inside `if self._client is None:`), and proceed straight
            # against the rejected collection. Keep `self._client` unset
            # until validation succeeds, so a retry re-validates from
            # scratch instead of silently bypassing it.
            self._client = client
            try:
                self._ensure_collection()
            except Exception:
                self._client = None
                raise
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
            return
        # ADR-0009: a collection created earlier — by a different embedder, a
        # different manifest, or before this check existed — is never
        # recreated here, so deriving/validating vector_size when
        # `_get_client()` first runs only protects the very first creation.
        # Catch a stale collection's real dimension before any upsert,
        # instead of letting Qdrant reject it with an opaque error.
        info = client.get_collection(self._collection)
        vectors_config = info.config.params.vectors
        if not hasattr(vectors_config, "size"):
            # A collection configured with named vectors (`dict[str, VectorParams]`
            # instead of a single unnamed `VectorParams`) has no single `.size` —
            # this store always creates unnamed collections (see the
            # `VectorParams(...)` call above with no `vector_name`), so this only
            # fires against a collection that predates this store or was created
            # by something else. Surfacing ConfigurationError here, rather than
            # letting the AttributeError propagate, keeps the "reject before use"
            # guarantee true for this shape too, even though this store cannot
            # itself produce or reconcile against named vectors.
            raise ConfigurationError(
                f"Qdrant collection {self._collection!r} uses named vectors, which "
                "QdrantStore does not support — it always indexes into a single "
                "unnamed default vector. Point at a different collection, or "
                "recreate this one without named vectors."
            )
        actual_size = vectors_config.size
        if actual_size != self._vector_size:
            raise ConfigurationError(
                f"Qdrant collection {self._collection!r} already exists with vector size "
                f"{actual_size}, but this pipeline's embedder produces "
                f"{self._vector_size}-dimensional vectors. Use a matching embedder, point "
                "at a different collection, or delete/recreate this one at the correct size."
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
