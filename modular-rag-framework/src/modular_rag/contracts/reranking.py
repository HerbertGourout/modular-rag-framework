from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


@runtime_checkable
class Reranker(Protocol):
    """Re-score and re-order retrieved Chunks for a Query."""

    def rerank(
        self,
        query: Query,
        chunks: list[RetrievedChunk],
        k: int = 5,
    ) -> list[RetrievedChunk]: ...

    def name(self) -> str: ...
