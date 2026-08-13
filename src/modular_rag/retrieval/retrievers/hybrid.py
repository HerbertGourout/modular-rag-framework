from __future__ import annotations

import threading

import structlog

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.fusion.rrf import reciprocal_rank_fusion
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever
from modular_rag.retrieval.retrievers.vector import VectorRetriever

log = structlog.get_logger(__name__)

# Keyed by the active lexical backend's own name() — not a hardcoded constant
# (Lot 5 — persistent sparse retrieval) — so lexical-only results are tagged
# with whichever backend actually produced them, not always RetrievalMethod.BM25.
_METHOD_BY_LEXICAL_NAME = {
    "bm25": RetrievalMethod.BM25,
    "sparse-qdrant": RetrievalMethod.SPARSE,
}


class HybridRetriever:
    """Combine dense (vector) and lexical retrieval via Reciprocal Rank Fusion.

    The lexical leg is manifest-selectable (Lot 5 — "rendre le backend
    sélectionnable par manifeste") via the
    `lexical_retriever` constructor argument: `app/default_factories.py`'s
    `"hybrid"` factory resolves a manifest's `retriever.config.lexical`
    (`"bm25-memory"`, the default, or `"sparse-qdrant"`) into a concrete
    object *before* constructing this class — `HybridRetriever` itself lives
    in `retrieval/` and cannot import the Qdrant-backed adapter directly
    (`scripts/check_layering.py` — domain modules cannot import `adapters/`),
    same reasoning as `retrieval.retrievers.vector.VectorRetriever`'s
    injected `_store`. `bm25_weight` keeps its name for manifest backward
    compatibility (both existing presets already set it) — it is the fusion
    weight for whichever lexical backend is configured, not specifically
    BM25's.
    """

    def __init__(
        self,
        # 0.7/0.3 is an engineering prior, unsourced by the research corpus
        # (docs/research/DIGEST-retrieval.md #5) — tune empirically on the golden set in V1.1.
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        collection: str = "documents",
        url: str = "http://localhost:6333",
        api_key: str = "",
        k: int = 20,
        reranker_k: int = 5,
        lexical_retriever: object | None = None,
    ) -> None:
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.k = k
        self.reranker_k = reranker_k
        self._vector = VectorRetriever(collection=collection, url=url, api_key=api_key)
        self._lexical = lexical_retriever if lexical_retriever is not None else BM25Retriever()
        # Lot 5: which source(s) raised during the most recent retrieve() call
        # (as opposed to legitimately returning zero results) — read by
        # RAGEngine._run_steps() (duck-typed, matching every other
        # Container-adjacent hasattr() check in that file) and folded into
        # the "retrieve" TraceStep's metadata, so a complete backend failure
        # is visible in observability instead of only a log line.
        #
        # architecture-reviewer finding (Lot 5): this HybridRetriever instance
        # is shared for the lifetime of the process (api/__init__.py's
        # create_app() builds one `pipeline`), and the API's sync `/answer`/
        # `/retrieve` endpoints run concurrently across worker threads. A
        # plain instance attribute here would let one request's
        # degraded-source signal leak into another's TraceStep, or be reset
        # out from under a concurrent read — the same hazard class
        # BM25Retriever's own threading.Lock already guards against for its
        # internal state. threading.local() gives every calling thread its
        # own independent value; the write (in retrieve()/_safe_retrieve())
        # and the read (RAGEngine._run_steps(), immediately after, same
        # synchronous call stack) always happen on the same thread.
        self._local = threading.local()

    def name(self) -> str:
        return "hybrid"

    @property
    def last_degraded_sources(self) -> list[str]:
        return list(getattr(self._local, "degraded_sources", []))

    def close(self) -> None:
        """Codex review (Lot 5, MED-001): `Container.close()` only reaches
        directly-registered components — the vector leg's client is owned by
        `Container.indexer` (`QdrantStore`), already closed separately (Lot
        14 precedent), so it is deliberately *not* closed here too. The
        lexical leg, when it's a `PersistentSparseRetriever`, owns its own
        `QdrantSparseStore` client that nothing else reaches — duck-typed
        (`BM25Retriever` has no `close()`, which is fine: nothing to release)."""
        close = getattr(self._lexical, "close", None)
        if close is not None:
            close()

    def index(self, chunks: list[Chunk]) -> int:
        """Feed the active lexical backend (Lot 5). Closes the gap that
        previously forced `RAGEngine.ingest_chunks()` to reach into the
        private `retriever._bm25` attribute directly — `HybridRetriever` had
        no `index()` at all before this."""
        return self._lexical.index(chunks)  # type: ignore[attr-defined,no-any-return]

    def delete(self, ids: list[str]) -> None:
        """Delegates to the active lexical side only. The vector side is
        owned separately via `Container.indexer` (`QdrantStore.delete()`),
        not by this retriever — `RAGEngine` coordinates both (Lot 12a,
        docs/refactoring-plan.md)."""
        self._lexical.delete(ids)  # type: ignore[attr-defined]

    def clear(self) -> None:
        self._lexical.clear()  # type: ignore[attr-defined]

    def list_ids(self) -> list[str]:
        """Delegates to the lexical side only — see `delete()`'s docstring
        for why (Lot 12b, docs/refactoring-plan.md)."""
        return self._lexical.list_ids()  # type: ignore[attr-defined,no-any-return]

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        self._local.degraded_sources = []
        lexical_method = _METHOD_BY_LEXICAL_NAME.get(
            self._lexical.name(),  # type: ignore[attr-defined]
            RetrievalMethod.BM25,
        )
        vector_hits = self._safe_retrieve(self._vector, query, k=k * 2, source="vector")
        lexical_hits = self._safe_retrieve(self._lexical, query, k=k * 2, source="lexical")

        if not vector_hits and not lexical_hits:
            if self.last_degraded_sources:
                # Lot 5: previously indistinguishable from "both sources
                # legitimately found nothing" — now a real backend failure
                # gets its own, higher-severity, differently-named event.
                log.error(
                    "hybrid.retrieved.empty_due_to_failure",
                    query_id=query.id,
                    degraded_sources=list(self.last_degraded_sources),
                )
            else:
                log.warning("hybrid.retrieved.empty", query_id=query.id)
            return []

        if not vector_hits:
            fused = lexical_hits[:k]
            for rank, chunk in enumerate(fused, 1):
                object.__setattr__(chunk, "rank", rank)
                object.__setattr__(chunk, "retrieval_method", lexical_method)
            log.debug(
                "hybrid.retrieved", chunks=len(fused), query_id=query.id, mode="lexical_only"
            )
            return fused

        if not lexical_hits:
            fused = vector_hits[:k]
            for rank, chunk in enumerate(fused, 1):
                object.__setattr__(chunk, "rank", rank)
                object.__setattr__(chunk, "retrieval_method", RetrievalMethod.VECTOR)
            log.debug("hybrid.retrieved", chunks=len(fused), query_id=query.id, mode="vector_only")
            return fused

        fused = reciprocal_rank_fusion(
            [vector_hits, lexical_hits],
            k=k,
            weights=[self.vector_weight, self.bm25_weight],
        )
        for rank, chunk in enumerate(fused, 1):
            object.__setattr__(chunk, "rank", rank)
            object.__setattr__(chunk, "retrieval_method", RetrievalMethod.HYBRID)
        log.debug("hybrid.retrieved", chunks=len(fused), query_id=query.id)
        return fused

    def _safe_retrieve(
        self,
        retriever: object,
        query: Query,
        *,
        k: int,
        source: str,
    ) -> list[RetrievedChunk]:
        try:
            return retriever.retrieve(query, k=k)  # type: ignore[attr-defined]
        except Exception as exc:
            log.warning(
                "hybrid.source_unavailable",
                source=source,
                query_id=query.id,
                error=exc.__class__.__name__,
            )
            self._local.degraded_sources.append(source)
            return []

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
