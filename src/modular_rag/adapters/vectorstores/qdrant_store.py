"""Qdrant vector store adapter — implements the Indexer and Retriever contracts."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitState,
    retry_with_backoff,
    unhealthy_dependency,
)

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

    from modular_rag.contracts.embeddings import Embedder

_DEFAULT_VECTOR_SIZE = 384
# Lot 6 (readiness and resilience): a probe-specific timeout bound, separate
# from `self._timeout` (the real connection-establishment budget used by
# `_get_client()`'s retrying path) — see `check_health()`'s cold-path
# handling below (orchestration-specialist review).
_HEALTH_CHECK_TIMEOUT = 5.0
T = TypeVar("T")


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
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._url = url
        self._collection = collection
        # Lot 6 (readiness and resilience): guards connection establishment
        # in _get_client() against transient network failures, and is read
        # (never mutated) by check_health() to fail fast without a network
        # round-trip once open. `circuit_breaker` is injectable so tests
        # never need to wait out a real `reset_timeout`.
        self._circuit = circuit_breaker or CircuitBreaker()
        # Guards the check-then-act lazy-init race in _get_client(): two
        # threads concurrently seeing `self._client is None` could otherwise
        # both construct a client and run _ensure_collection(), leaking one
        # (Codex-style finding, Lot 6 — this store is now reached
        # concurrently by real traffic *and* /ready's own health probes).
        self._init_lock = threading.Lock()
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
        self._client: QdrantClient | None = None  # lazy
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

    def _get_client(self) -> QdrantClient:
        if self._client is not None:
            return self._client
        with self._init_lock:
            if self._client is not None:  # another thread won the race while we waited
                return self._client
            if self._embedder is not None:
                self.ensure_vector_size(self._embedder.dimensions)
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.http.exceptions import ResponseHandlingException
            except ImportError as exc:
                raise ImportError(
                    "qdrant-client is required for QdrantStore. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc

            def _connect() -> None:
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

            # Lot 6 (readiness and resilience): `ResponseHandlingException` is
            # qdrant-client's actual exception for a real connection failure
            # (verified live against a refused connection — its own base
            # `ApiException` does *not* subclass `ConnectionError`, so the
            # default `retryable=(ConnectionError, TimeoutError)` would never
            # match it). `ConfigurationError` (dimension/named-vector mismatch,
            # raised inside `_ensure_collection()`) is deliberately excluded —
            # retrying a genuine configuration mistake wastes 3 attempts
            # before surfacing the same actionable error, since the manifest
            # doesn't change between retries.
            self._circuit.call(
                lambda: retry_with_backoff(
                    _connect,
                    retryable=(ResponseHandlingException, ConnectionError, TimeoutError),
                )
            )
        # `retry_with_backoff`/`self._circuit.call()` re-raise on failure
        # rather than returning, so reaching here means `_connect()`
        # succeeded and `self._client` is set — this lets mypy narrow the
        # type across the closure boundary instead of treating it as
        # possibly `None` (same pattern as QdrantSparseStore._get_client()).
        assert self._client is not None
        return self._client

    def _call(self, op: Callable[[QdrantClient], T]) -> T:
        """Route a post-init client operation through the same retry+
        circuit-breaker discipline `_get_client()` already applies to
        connection establishment (Codex review HIGH-003, Lot 6): previously
        only the initial connect was protected — a dependency that failed
        *after* the first successful connect (the ordinary production
        failure mode, not just a cold start) was retried by nothing and its
        failures never reopened the circuit, so every subsequent request
        kept hitting a known-broken Qdrant at full rate. Every caller of
        this helper (`index`/`delete`/`clear`/`list_ids`/
        `retrieve_by_vector`) is naturally idempotent (point-ID upsert or
        delete, read-only scroll/query) — see the Lot 6 acceptance
        criterion "ne retry que les opérations sûres ou idempotentes."

        `self._get_client()` is called once, upfront, *outside* the retry
        loop below — deliberately not nested inside it. `_get_client()` has
        its own bounded retry+circuit sequence for a cold connect; wrapping
        that a second time here would compound into up to 3×3 attempts
        instead of 3. Once connected, `self._get_client()` is a cheap
        cached-return, so calling it again inside `_attempt()` on each retry
        just re-fetches the same client — qdrant-client manages its own
        HTTP/gRPC connection pooling internally and does not hold one
        single stateful socket the way a raw `psycopg` connection does, so
        (unlike the Postgres adapters) there is no separate "connection"
        object to invalidate and recreate here — simply retrying the
        operation against the same client is the correct fix.
        """
        from qdrant_client.http.exceptions import ResponseHandlingException

        self._get_client()  # ensure connected; its own retry+circuit path owns the cold case

        def _attempt() -> T:
            return op(self._get_client())

        return self._circuit.call(
            lambda: retry_with_backoff(
                _attempt,
                retryable=(ResponseHandlingException, ConnectionError, TimeoutError),
            )
        )

    def _ensure_collection(self) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        # Only ever called from _get_client() immediately after `self._client
        # = client` (a real, just-constructed QdrantClient) — this assert
        # lets mypy narrow the type across the method boundary instead of
        # treating `self._client` as possibly None here (Lot 6 — same
        # pattern already used in QdrantSparseStore._ensure_collection()).
        assert self._client is not None
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
        # mypy can't narrow `VectorParams | dict[str, VectorParams] | None`
        # through the `hasattr()` check above the way it would through
        # `isinstance()` — the check itself already guarantees this at
        # runtime (Lot 6: surfaced now that `_get_client()`'s return type is
        # `QdrantClient`, not implicitly `Any`).
        actual_size = vectors_config.size  # type: ignore[union-attr]
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
                    # Codex review (Lot 5, HIGH-001): `**chunk.metadata` must be
                    # spread FIRST, not last — a chunk indexed after
                    # TenantIsolationPolicy.enforce_ingest() validated
                    # chunk.tenant_id could still carry a caller-supplied
                    # metadata["tenant_id"] (Chunk.metadata accepts any key
                    # unvalidated). Writing the structured fields *after* the
                    # spread guarantees they always win regardless of dict
                    # order — this exact ordering bug was reproduced and fixed
                    # in the new QdrantSparseStore.index() first; applied here
                    # too for dense/sparse parity (this store had the same bug
                    # already, predating this Lot).
                    payload={
                        **chunk.metadata,
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
                        # classification persisted explicitly (Lot 20, Codex review pass 1,
                        # HIGH-003): same bug shape as tenant_id above -- previously dropped
                        # here and never reconstructed in retrieve_by_vector(), which
                        # silently defeated governance.egress_policy for the real Qdrant
                        # path (every chunk round-tripped through Qdrant came back with
                        # classification=None, indistinguishable from genuinely unclassified
                        # content -- the policy's own default_classification then applied,
                        # which can incorrectly deny permitted content or, with a permissive
                        # default, incorrectly allow restricted content).
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
        """Enumerate every point id currently in the collection, via Qdrant's
        scroll API (no vectors/payload fetched — id listing only). Added in
        Lot 12b (docs/refactoring-plan.md) for `orchestration.reconciliation.IndexReconciler`
        to detect divergence against the lexical index / lifecycle ledger."""
        ids: list[str] = []
        offset = None
        while True:
            # Codex review MED-003 (Lot 6, second pass): a bare `lambda`
            # capturing the loop variable `offset` is safe at runtime here
            # (`self._call()` invokes it synchronously, in the same
            # statement that reassigns `offset`, so the closure never
            # outlives this iteration) but Ruff's `B023` flags it anyway —
            # it can't see that synchronous-call guarantee, only that a
            # function is defined inside a loop and references a loop
            # variable. A named `def` with the current value bound as a
            # real default argument satisfies the lint rule and gives mypy
            # a properly-typed callable to check against `_call()`'s
            # `Callable[[QdrantClient], T]` (a bare `lambda` with a default
            # argument here previously produced "Cannot infer type of
            # lambda").
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

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Lot 6 — readiness
        and resilience). Two cheap, read-only round-trips
        (`get_collections()` + `get_collection()` — metadata only, no
        scan).

        Reads (never writes) `self._circuit`'s state to fail fast without a
        network call when already OPEN. Once a client is cached (from prior
        real traffic or an earlier health check), this method's own calls
        are *not* fed back into `_record_success`/`_record_failure` — a
        periodic probe must not reset real-traffic failure accounting or
        race a live request for the single HALF_OPEN trial.

        Cold path (no client cached yet): revised per orchestration-specialist
        review, Lot 6. This used to call `_get_client()` directly, which
        meant a probe against a genuinely-down dependency went through
        `self._init_lock` (blocking every real request thread waiting on the
        same lock), `retry_with_backoff` (up to 3 attempts against
        `self._timeout`, up to ~90s total), and `_ensure_collection()`
        (which can call `create_collection()` — a write side effect a
        readiness probe must never have). Instead, a bare, throwaway client
        is constructed here: single attempt, the short `_HEALTH_CHECK_TIMEOUT`
        bound (not `self._timeout`), no lock, no retry, no collection
        creation, and nothing cached onto `self`. The eventual real
        connection — driven by real traffic or a later health check once one
        exists — still goes through the full retry+circuit path in
        `_get_client()`, unaffected by this probe. This throwaway client is
        closed in a `finally` regardless of the outcome (Codex review
        MEDIUM-002, fourth pass) — never left for the garbage collector, and
        never the warm, shared `self._client`, which this method never
        closes.

        Collection validation (Codex review HIGH-001, second pass): a
        reachable Qdrant server previously reported healthy even if the
        configured collection didn't exist, used named vectors, or had the
        wrong dimension — `get_collections()` alone only proves the server
        answers, not that this store could actually write or read through
        it. The real validation ran once, lazily, inside
        `_ensure_collection()` — meaning a readiness probe against a
        reachable-but-misconfigured Qdrant (a common shape right after a
        deploy or restore against the wrong collection) stayed green until
        the first real request discovered the mismatch. This now performs
        the same checks `_ensure_collection()` does when creating, but
        read-only — a missing collection is reported unhealthy here, never
        silently created by a probe.
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
                # Codex review MEDIUM-002 (Lot 6, fourth pass): the
                # throwaway cold-path client (its own HTTP transport/
                # connection pool) was never closed on any exit path —
                # never cached onto `self._client`, so `Container.close()`
                # can never reach it either. A periodic orchestrator probe
                # against a not-yet-connected store would leak one transport
                # per probe until real traffic finally connects. The warm,
                # shared `self._client` is never closed here — only a
                # genuinely cold, throwaway one this method itself
                # constructed.
                if is_cold:
                    try:
                        client.close()
                    except Exception:
                        pass  # best-effort cleanup; must not mask the health result
        except Exception as exc:
            # Codex review MED-002 (Lot 6): /ready is unauthenticated —
            # never put a raw exception message (can embed hostnames,
            # collection names, SDK internals) into the public response.
            return [unhealthy_dependency(self.name(), exc, (time.perf_counter() - t0) * 1000)]

    def _probe_collection(self, client: QdrantClient, t0: float) -> list[DependencyHealth]:
        """The read-only collection/dimension validation body of
        `check_health()`, split out so that method can close a cold,
        throwaway client in a `finally` regardless of which of these
        branches returns (Codex review MEDIUM-002, Lot 6, fourth pass).
        Exceptions propagate to the caller's classification/logging."""
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
        vectors_config = info.config.params.vectors
        if not hasattr(vectors_config, "size"):
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail="collection uses named vectors, which this store does not support",
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        actual_size = vectors_config.size  # type: ignore[union-attr]
        # Codex review HIGH-003 (Lot 6, fourth pass) / HIGH-002 (Lot 6,
        # fifth pass): history of this comparison — the third-pass fix
        # avoided comparing against a not-yet-derived default by skipping
        # the numeric comparison whenever cold + non-explicit, which
        # reintroduced the *original* gap (a genuinely incompatible
        # collection reported healthy until real traffic hit it). The
        # fourth-pass fix resolved the expected size from
        # `self._embedder.dimensions` directly — but that property is not
        # universally free: for a `HuggingFaceEmbedder` model name outside
        # its static known-model table, `.dimensions` calls `_get_model()`,
        # which imports `sentence_transformers` and downloads/loads the
        # real model, with no timeout and no lock against several
        # concurrent probes each starting their own redundant load
        # (confirmed by reading `_get_model()` directly) — a readiness
        # probe must never risk that, the same principle already applied to
        # never calling the LLM from a generator probe or ever writing from
        # a Qdrant probe. Resolved by a cheap-only, duck-typed extension
        # instead: `known_dimensions()` (optional, like `check_health()`
        # itself), implemented by every embedder in this codebase to return
        # its dimension *only* when that's free to compute — `None`
        # otherwise, never a fallback to the loading path. If unavailable
        # (an embedder that doesn't implement it, or a genuinely
        # unrecognized custom HF model name, or no embedder bound at all),
        # this falls back to `self._vector_size` — the same best-available
        # guess already used for the "no embedder bound" case — rather than
        # ever risking a real model load from `/ready`. The resolved value
        # is used only for this comparison, never written back to
        # `self._vector_size` — a probe must not mutate state a real
        # request also depends on (ADR-0010 §4).
        known_dimensions = getattr(self._embedder, "known_dimensions", None)
        resolved = known_dimensions() if known_dimensions is not None else None
        if self._vector_size_explicit or resolved is None:
            expected_size = self._vector_size
        else:
            expected_size = resolved
        if actual_size != expected_size:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=(
                        f"collection vector size {actual_size} does not match "
                        f"expected {expected_size}"
                    ),
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
            ]
        return [
            DependencyHealth(
                name=self.name(), healthy=True, latency_ms=(time.perf_counter() - t0) * 1000
            )
        ]

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
        query_filter = None
        if tenant_id is not None:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            query_filter = Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
            )
        # Codex review HIGH-001 (Lot 6): migrated from `client.search()`,
        # which does not exist on `qdrant-client==1.18.0` — confirmed live,
        # `hasattr(QdrantClient, "search")` is `False` — so every real call
        # to this method previously raised `AttributeError` against the
        # actually-pinned dependency. `query_points()` is the SDK's current,
        # unified search entrypoint. This collection's dense vector is
        # unnamed/default (see `_ensure_collection()`'s
        # `VectorParams(...)` call with no vector name), so `query=vector`
        # alone selects it — no `using=` needed (that's only for named
        # vectors; contrast `QdrantSparseStore.retrieve_by_text()`'s
        # identical call shape, which does need `using=_VECTOR_NAME`).
        # Routed through `self._call()` (Codex review HIGH-003) so a
        # post-init failure here is retried and counted by the circuit
        # breaker like every other operation, not just the initial connect.
        result = self._call(
            lambda client: client.query_points(
                collection_name=self._collection,
                query=vector,
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
                    retrieval_method=RetrievalMethod.VECTOR,
                )
            )
        return results
