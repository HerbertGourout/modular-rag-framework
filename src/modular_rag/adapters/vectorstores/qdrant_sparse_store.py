"""Qdrant sparse-vector store adapter — persistent lexical retrieval backend
for durable deployments (Lot 5 — "replace in-memory BM25 with a persistent
sparse retrieval"). Implements `contracts.indexing.
Indexer` against a dedicated Qdrant collection, separate from `QdrantStore`'s
dense-vector collection: entangling the two would make `QdrantStore` (a pure
`VectorIndexer`) carry a sparse-retrieval concern it was never designed for,
and would break the existing dual-store coordination pattern `RAGEngine`
already runs for the lexical side (`_delete_chunk_ids`/`ingest_chunks`
coordinate `Container.indexer` and `Container.retriever` as two independent
stores — exactly how in-memory BM25 works today).

Unlike `QdrantStore` (which requires the caller to pre-compute
`chunk.embedding` via a separately-wired `Embedder`), this store computes its
own sparse vectors from `chunk.content` directly — there is no pluggable
"sparse embedder" component in this framework, and adding one would touch
`RAGEngine.ingest_chunks()` and the manifest schema for a fixed, cheap,
deterministic function that does not benefit from being swappable. This
mirrors `retrieval.retrievers.bm25.BM25Retriever`'s self-contained
tokenization, not `QdrantStore`'s externally-supplied-embedding design.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.sparse_vectorizer import index_sparse_vector, query_sparse_vector

if TYPE_CHECKING:
    # Codex review (Lot 5, HIGH-003): type-only import so mypy can check
    # `_get_client()`'s return type and `_ensure_collection()`'s use of
    # `self._client` without the module-level import CLAUDE.md §05.7's lazy
    # import rule for qdrant-client actually forbids.
    from qdrant_client import QdrantClient

_VECTOR_NAME = "sparse"
# test-specialist review (Lot 5): the original comment here claimed this
# matched "manifests/presets chunk_size=512 defaults (~100-130 words per
# chunk)" — wrong. `ingestion.chunkers.fixed.FixedSizeChunker`'s `chunk_size`
# is *token*-counted (its own docstring: "chunk_size and chunk_overlap count
# tokens via a pluggable token_counter", default counter = whitespace word
# count, matching Chunk.token_estimate) — so a chunk_size=512 chunk averages
# ~512 words, not ~100-130. 512 matches that default directly. Still a fixed,
# configured constant rather than a running corpus average — see
# core.sparse_vectorizer.index_sparse_vector's docstring for why.
_DEFAULT_AVGDL = 512.0


class QdrantSparseStore:
    """Wraps qdrant-client to provide `Indexer` behaviour against a
    sparse-only Qdrant collection (`Modifier.IDF`, no dense vector field).

    Deliberately narrower than `QdrantStore`: no `Retriever.retrieve()` —
    callers use `retrieve_by_text()` (analogous to `QdrantStore.
    retrieve_by_vector()`, but taking raw query text since sparse
    vectorization is this store's own responsibility, not an externally
    wired `Embedder`'s).
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "mrag_sparse_default",
        api_key: str | None = None,
        timeout: float = 30.0,
        avgdl: float = _DEFAULT_AVGDL,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        # test-specialist review (Lot 5): `avgdl` reaches here from manifest
        # config unvalidated. `dl / avgdl` in core.sparse_vectorizer.
        # index_sparse_vector divides by this on every indexed chunk — a
        # zero or negative value raised a bare, unactionable
        # ZeroDivisionError/produced a nonsensical negative-weight sparse
        # vector deep inside the first index() call, not at construction.
        # Same fail-fast-at-construction pattern as DeterministicEmbedder's
        # `dimensions` / DeterministicGenerator's `max_chunks` validation.
        if avgdl <= 0:
            raise ConfigurationError(
                f"QdrantSparseStore avgdl must be a positive number, got {avgdl}."
            )
        self._url = url
        self._collection = collection
        self._api_key = api_key
        self._timeout = timeout
        self._avgdl = avgdl
        self._k1 = k1
        self._b = b
        self._client: QdrantClient | None = None  # lazy

    def name(self) -> str:
        return "sparse-qdrant"

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise ImportError(
                    "qdrant-client is required for QdrantSparseStore. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc

            client = QdrantClient(
                url=self._url, api_key=self._api_key, timeout=int(self._timeout)
            )
            # Same publish-after-validate discipline as QdrantStore._get_client()
            # (Codex review, second pass, HIGH-002 on that store): a retry after
            # a failed _ensure_collection() must re-validate, not silently reuse
            # a never-actually-checked client.
            self._client = client
            try:
                self._ensure_collection()
            except Exception:
                # Codex review (Lot 5, MED-001): the rejected client's own
                # HTTP transport was previously never closed here — just
                # discarded by clearing `self._client`. A caller that
                # retries (e.g. against a still-incompatible collection
                # during a migration) leaks one more open connection per
                # attempt. close() itself is best-effort: a failure closing
                # an already-broken client must not mask the original
                # validation error.
                try:
                    client.close()
                except Exception:
                    pass
                self._client = None
                raise
        return self._client

    def _ensure_collection(self) -> None:
        from qdrant_client.http.models import Modifier, SparseIndexParams, SparseVectorParams

        # Only ever called from _get_client() immediately after `self._client
        # = client` (a real, just-constructed QdrantClient) — this assert
        # lets mypy narrow the type across the method boundary instead of
        # treating `self._client` as possibly None here (Codex review, Lot 5,
        # HIGH-003).
        assert self._client is not None
        client = self._client
        existing = [c.name for c in client.get_collections().collections]
        if self._collection not in existing:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=None,
                sparse_vectors_config={
                    _VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(),
                        modifier=Modifier.IDF,
                    )
                },
            )
            return
        # Same "reject a stale/foreign collection before any upsert" guarantee
        # as QdrantStore._ensure_collection() — a collection created earlier
        # without the expected sparse field name would otherwise surface as an
        # opaque error deep inside index()/retrieve_by_text() instead of here.
        info = client.get_collection(self._collection)
        sparse_config = info.config.params.sparse_vectors
        if not sparse_config or _VECTOR_NAME not in sparse_config:
            raise ConfigurationError(
                f"Qdrant collection {self._collection!r} has no sparse vector field "
                f"{_VECTOR_NAME!r} — QdrantSparseStore requires a sparse-only collection "
                "created with modifier=Modifier.IDF. Point at a different collection, or "
                "delete/recreate this one."
            )
        # Codex review (Lot 5, MED-001): the field-name check above passes
        # for a collection whose sparse field is named "sparse" but was
        # created with the default modifier (`Modifier.NONE`, not IDF) —
        # `SparseVectorParams.modifier` defaults to `none`, not `idf`.
        # index_sparse_vector() deliberately computes only BM25's saturated
        # term-frequency component and leaves IDF weighting to Qdrant's
        # Modifier.IDF (see core.sparse_vectorizer's module docstring) — a
        # collection without it silently returns TF-only scores, not the
        # BM25-like ranking this store's docstring and error messages
        # promise, with no error to signal the mismatch.
        actual_modifier = sparse_config[_VECTOR_NAME].modifier
        if actual_modifier != Modifier.IDF:
            raise ConfigurationError(
                f"Qdrant collection {self._collection!r}'s sparse vector field "
                f"{_VECTOR_NAME!r} has modifier={actual_modifier!r}, not Modifier.IDF — "
                "QdrantSparseStore requires IDF weighting to be enabled server-side (this "
                "store's own vectorization deliberately omits IDF, relying on Qdrant to supply "
                "it). Point at a different collection, or delete/recreate this one so it's "
                "created with modifier=Modifier.IDF."
            )

    # ------------------------------------------------------------------
    # Indexer contract
    # ------------------------------------------------------------------

    def index(self, chunks: list[Chunk]) -> int:
        from qdrant_client.http.models import PointStruct, SparseVector

        client = self._get_client()
        points = []
        for chunk in chunks:
            sparse = index_sparse_vector(
                chunk.content, avgdl=self._avgdl, k1=self._k1, b=self._b
            )
            if not sparse:
                # Degenerate input (empty content, or no \w tokens) — nothing to
                # index; an empty sparse vector cannot be upserted or searched
                # meaningfully (core.sparse_vectorizer.index_sparse_vector's
                # docstring; retrieval-specialist review).
                continue
            points.append(
                PointStruct(
                    id=chunk.id,
                    vector={
                        _VECTOR_NAME: SparseVector(
                            indices=list(sparse.keys()), values=list(sparse.values())
                        )
                    },
                    # Codex review (Lot 5, HIGH-001): `**chunk.metadata` must be
                    # spread FIRST, not last — a chunk indexed after
                    # TenantIsolationPolicy.enforce_ingest() validated
                    # chunk.tenant_id could still carry a caller-supplied
                    # metadata["tenant_id"] (Chunk.metadata accepts any key
                    # unvalidated). Writing the structured fields *after* the
                    # spread guarantees they always win regardless of dict
                    # order — reproduced and confirmed before this fix: a
                    # chunk with tenant_id="tenant-a" and
                    # metadata={"tenant_id": "tenant-b"} silently indexed as
                    # tenant-b, defeating tenant isolation for the sparse
                    # partition (the server-side filter in retrieve_by_text()
                    # then filters on this same falsified value). Same fix
                    # applied to QdrantStore.index() for dense/sparse parity.
                    payload={
                        **chunk.metadata,
                        "doc_id": chunk.doc_id,
                        "content": chunk.content,
                        "modality": chunk.modality,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "page": chunk.page,
                        "tenant_id": chunk.tenant_id,
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

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Sparse search — analogous to QdrantStore.retrieve_by_vector(), but
    # taking raw query text (see module docstring for why).
    # ------------------------------------------------------------------

    def retrieve_by_text(
        self, query_text: str, k: int = 10, tenant_id: str | None = None
    ) -> list[RetrievedChunk]:
        sparse = query_sparse_vector(query_text)
        if not sparse:
            return []
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue, SparseVector

        client = self._get_client()
        query_filter = None
        if tenant_id is not None:
            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )
        result = client.query_points(
            collection_name=self._collection,
            query=SparseVector(indices=list(sparse.keys()), values=list(sparse.values())),
            using=_VECTOR_NAME,
            query_filter=query_filter,
            limit=k,
        )
        results = []
        for rank, hit in enumerate(result.points, 1):
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
                    retrieval_method=RetrievalMethod.SPARSE,
                )
            )
        return results
