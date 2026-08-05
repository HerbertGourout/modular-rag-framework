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

    def list_ids(self) -> list[str]:
        """Enumerate every chunk id currently in the corpus. Added in Lot 12b
        (docs/refactoring-plan.md) so `orchestration.reconciliation.IndexReconciler`
        can detect divergence against the vector index / lifecycle ledger."""
        return [c.id for c in self._chunks]

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
        """Rank by BM25 score, but gate inclusion on genuine lexical overlap
        rather than `score > 0` (fixed in Lot 12b, docs/refactoring-plan.md).

        `rank_bm25`'s IDF term can be zero or negative when a query term
        appears in most/all documents of a small corpus — trivially likely
        with only 1-2 chunks indexed. The old `score > 0` filter then dropped
        a chunk that is the best, or only, lexical match for the query
        (confirmed directly against `BM25Okapi`: a 1-document corpus scores
        its only document negative for its own content). Gating on whether
        the query and chunk share at least one token instead keeps that
        chunk while still excluding chunks with zero term overlap at all
        (see tests/unit/retrieval/test_bm25.py's regression tests for both
        directions).
        """
        if self._bm25 is None or not self._chunks:
            return []
        query_tokens = set(query.text.lower().split())
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query.text.lower().split())  # type: ignore[attr-defined]
        candidates = [
            (idx, score)
            for idx, score in enumerate(scores)
            if query_tokens & set(self._chunks[idx].content.lower().split())
        ]
        candidates.sort(key=lambda pair: pair[1], reverse=True)
        return [
            RetrievedChunk(
                chunk=self._chunks[idx],
                score=float(score),
                rank=rank,
                retrieval_method=RetrievalMethod.BM25,
            )
            for rank, (idx, score) in enumerate(candidates[:k], 1)
        ]

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
