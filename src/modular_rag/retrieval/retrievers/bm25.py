from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class BM25Retriever:
    """In-memory BM25 retriever using rank-bm25.

    `index()` appends to (not replaces) the existing corpus, rebuilding the
    underlying `BM25Okapi` model each call — `rank_bm25` has no incremental
    update API, so a full rebuild is the only option; a second `index()` call
    is expected to add to a growing corpus, not silently drop the first
    (fixed in Lot 12a, docs/refactoring-plan.md — see
    tests/unit/retrieval/test_bm25.py's regression test for the pre-fix
    behavior this replaces). `delete()`/`clear()` close the exact structural
    gap named in docs/refactoring-plan.md §2 ("BM25Retriever implements no
    delete()/clear() either").
    """

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._bm25: object | None = None

    def name(self) -> str:
        return "bm25"

    def index(self, chunks: list[Chunk]) -> None:
        self._chunks.extend(chunks)
        self._rebuild()

    def delete(self, ids: list[str]) -> None:
        id_set = set(ids)
        self._chunks = [c for c in self._chunks if c.id not in id_set]
        self._rebuild()

    def clear(self) -> None:
        self._chunks = []
        self._bm25 = None

    def _rebuild(self) -> None:
        if not self._chunks:
            self._bm25 = None
            return
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError("Install 'rank-bm25' (pip install modular-rag[v1]).") from exc

        tokenized = [c.content.lower().split() for c in self._chunks]
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
            for rank, (idx, score) in enumerate(ranked, 1)
            if score > 0
        ]

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
