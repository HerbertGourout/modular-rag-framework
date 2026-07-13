from __future__ import annotations

import structlog

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.retrieval.fusion.rrf import reciprocal_rank_fusion
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever
from modular_rag.retrieval.retrievers.vector import VectorRetriever

log = structlog.get_logger(__name__)


class HybridRetriever:
    """Combine dense (vector) and sparse (BM25) retrieval via Reciprocal Rank Fusion."""

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
    ) -> None:
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.k = k
        self.reranker_k = reranker_k
        self._vector = VectorRetriever(collection=collection, url=url, api_key=api_key)
        self._bm25 = BM25Retriever()

    def name(self) -> str:
        return "hybrid"

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        vector_hits = self._vector.retrieve(query, k=k * 2)
        bm25_hits = self._bm25.retrieve(query, k=k * 2)
        fused = reciprocal_rank_fusion(
            [vector_hits, bm25_hits],
            k=k,
            weights=[self.vector_weight, self.bm25_weight],
        )
        for rank, chunk in enumerate(fused, 1):
            object.__setattr__(chunk, "rank", rank)
            object.__setattr__(chunk, "retrieval_method", RetrievalMethod.HYBRID)
        log.debug("hybrid.retrieved", chunks=len(fused), query_id=query.id)
        return fused

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
