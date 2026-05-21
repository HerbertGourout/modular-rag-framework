from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class BM25Retriever:
    """In-memory BM25 retriever using rank-bm25."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._bm25: object | None = None

    def name(self) -> str:
        return "bm25"

    def index(self, chunks: list[Chunk]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError("Install 'rank-bm25' (pip install modular-rag[v1]).") from exc

        self._chunks = chunks
        tokenized = [c.content.lower().split() for c in chunks]
        self._bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        if self._bm25 is None or not self._chunks:
            return []
        tokens = query.text.lower().split()
        scores = self._bm25.get_scores(tokens)  # type: ignore[union-attr]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]
        return [
            RetrievedChunk(
                chunk=self._chunks[idx],
                score=float(score),
                rank=rank,
                retrieval_method=RetrievalMethod.BM25,
            )
            for rank, (idx, score) in enumerate(ranked)
            if score > 0
        ]

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
