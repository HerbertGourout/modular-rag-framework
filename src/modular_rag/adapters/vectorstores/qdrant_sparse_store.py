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

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitState,
    retry_with_backoff,
    unhealthy_dependency,
)
from modular_rag.core.sparse_vectorizer import index_sparse_vector, query_sparse_vector

if TYPE_CHECKING:
    # Codex review (Lot 5, HIGH-003): type-only import so mypy can check
    # `_get_client()`'s return type and `_ensure_collection()`'s use of
    # `self._client` without the module-level import CLAUDE.md §05.7's lazy
    # import rule for qdrant-client actually forbids.
    from qdrant_client import QdrantClient

# Lot 6 (readiness and resilience): see QdrantStore's identical constant for
# the full rationale.
_HEALTH_CHECK_TIMEOUT = 5.0
T = TypeVar("T")
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
        circuit_breaker: CircuitBreaker | None = None,
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
        # Lot 6 (readiness and resilience): see QdrantStore's identical
        # fields for the full rationale — connection-establishment retry/
        # circuit-breaking, and guarding the check-then-act lazy-init race
        # now that this store is reached concurrently by real traffic and
        # /ready's own health probes.
        self._circuit = circuit_breaker or CircuitBreaker()
        self._init_lock = threading.Lock()

    def name(self) -> str:
        return "sparse-qdrant"

    def _get_client(self) -> QdrantClient:
        if self._client is not None:
            return self._client
        with self._init_lock:
            if self._client is not None:
                return self._client
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.http.exceptions import ResponseHandlingException
            except ImportError as exc:
                raise ImportError(
                    "qdrant-client is required for QdrantSparseStore. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc

            def _connect() -> None:
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

            # Lot 6: see QdrantStore._get_client() for why
            # ResponseHandlingException specifically (verified live) and why
            # ConfigurationError (dimension/modifier mismatch, raised inside
            # _ensure_collection()) is deliberately excluded from retryable.
            self._circuit.call(
                lambda: retry_with_backoff(
                    _connect,
                    retryable=(ResponseHandlingException, ConnectionError, TimeoutError),
                )
            )
        # `retry_with_backoff`/`self._circuit.call()` re-raise on failure
        # rather than returning, so reaching here means `_connect()`
        # succeeded and `self._client` is set (Lot 6 — mirrors
        # QdrantStore._get_client()'s identical narrowing).
        assert self._client is not None
        return self._client

    def _call(self, op: Callable[[QdrantClient], T]) -> T:
        """Route a post-init client operation through retry+circuit-breaker
        (Codex review HIGH-003, Lot 6) — see `QdrantStore._call()` for the
        full rationale, including why `self._get_client()` is invoked once,
        upfront, outside the retry loop rather than nested inside it."""
        from qdrant_client.http.exceptions import ResponseHandlingException

        self._get_client()

        def _attempt() -> T:
            return op(self._get_client())

        return self._circuit.call(
            lambda: retry_with_backoff(
                _attempt,
                retryable=(ResponseHandlingException, ConnectionError, TimeoutError),
            )
        )

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
                        # classification persisted explicitly (Lot 20, Codex review pass 1,
                        # HIGH-003) -- same tenant_id-shaped bug, same fix; see
                        # QdrantStore.index()'s identical comment for the full rationale.
                        "classification": chunk.classification,
                    },
                )
            )
        if points:
            self._call(
                lambda client: client.upsert(collection_name=self._collection, points=points)
            )
        else:
            self._get_client()  # preserve prior behavior: still validate connectivity/collection
        return len(points)

    def delete(self, chunk_ids: list[str]) -> None:
        from qdrant_client.http.models import PointIdsList

        self._call(
            lambda client: client.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=chunk_ids),
            )
        )

    def clear(self) -> None:
        def _op(client: QdrantClient) -> None:
            client.delete_collection(collection_name=self._collection)
            self._ensure_collection()

        self._call(_op)

    def list_ids(self) -> list[str]:
        ids: list[str] = []
        offset = None
        while True:
            # Codex review MED-003 (Lot 6, second pass): see
            # QdrantStore.list_ids() for the full rationale — a bare
            # `lambda` capturing `offset` is runtime-safe here but trips
            # Ruff's `B023`, and a `lambda` with a default argument
            # previously confused mypy's `Callable` inference.
            def _scroll(client: QdrantClient, _offset: Any = offset) -> Any:
                return client.scroll(
                    collection_name=self._collection,
                    limit=256,
                    offset=_offset,
                    with_payload=False,
                    with_vectors=False,
                )

            points, offset = self._call(_scroll)
            ids.extend(str(p.id) for p in points)
            if offset is None:
                break
        return ids

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). See `QdrantStore.check_health()` for the full
        rationale (single fast attempt, no retry; reads but never mutates
        `self._circuit`; a cold, never-connected store probes with a bare
        throwaway client instead of `_get_client()`, so a down dependency
        can't block real request threads on `self._init_lock` or trigger
        `create_collection()` as a side effect).

        Collection validation (Codex review HIGH-001, second pass): mirrors
        `_ensure_collection()`'s read-only checks — existence, the expected
        sparse field name, and `Modifier.IDF` — so a reachable-but-wrong
        collection (missing the sparse field, or present but not
        IDF-weighted, silently returning TF-only scores) is reported
        unhealthy here instead of staying green until the first real
        `index()`/`retrieve_by_text()` call. The cold-path throwaway client
        is closed in a `finally` regardless of the outcome (Codex review
        MEDIUM-002, fourth pass) — see `QdrantStore.check_health()` for the
        full rationale; the warm, shared `self._client` is never closed
        here.
        """
        t0 = time.perf_counter()
        if self._circuit.state == CircuitState.OPEN:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail="circuit open",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        is_cold = self._client is None
        try:
            if not is_cold:
                assert self._client is not None  # narrows across the is_cold check for mypy
                client = self._client
            else:
                from qdrant_client import QdrantClient

                probe_timeout = max(1, round(min(self._timeout, _HEALTH_CHECK_TIMEOUT)))
                client = QdrantClient(url=self._url, api_key=self._api_key, timeout=probe_timeout)
            try:
                return self._probe_collection(client, t0)
            finally:
                if is_cold:
                    try:
                        client.close()
                    except Exception:
                        pass  # best-effort cleanup; must not mask the health result
        except Exception as exc:
            # Codex review MED-002 (Lot 6): see QdrantStore.check_health()
            # for the rationale — /ready is unauthenticated.
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]

    def _probe_collection(self, client: QdrantClient, t0: float) -> list[DependencyHealth]:
        """See `QdrantStore._probe_collection()` for why this is split out
        of `check_health()` (Codex review MEDIUM-002, Lot 6, fourth pass)."""
        existing = [c.name for c in client.get_collections().collections]
        if self._collection not in existing:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=f"collection {self._collection!r} does not exist",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        info = client.get_collection(self._collection)
        sparse_config = info.config.params.sparse_vectors
        if not sparse_config or _VECTOR_NAME not in sparse_config:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=f"collection has no sparse vector field {_VECTOR_NAME!r}",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        from qdrant_client.http.models import Modifier

        actual_modifier = sparse_config[_VECTOR_NAME].modifier
        if actual_modifier != Modifier.IDF:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=f"sparse vector field modifier={actual_modifier!r}, not IDF",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        return [
            DependencyHealth(
                name=self.name(), healthy=True, latency_ms=(time.perf_counter() - t0) * 1000
            )
        ]

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

        query_filter = None
        if tenant_id is not None:
            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )
        # Codex review HIGH-003 (Lot 6): routed through `self._call()` so a
        # post-init failure here is retried and counted by the circuit
        # breaker like every other operation, not just the initial connect.
        result = self._call(
            lambda client: client.query_points(
                collection_name=self._collection,
                query=SparseVector(indices=list(sparse.keys()), values=list(sparse.values())),
                using=_VECTOR_NAME,
                query_filter=query_filter,
                limit=k,
            )
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
                classification=payload.get("classification"),
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
                        "classification",
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
