from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


@runtime_checkable
class Retriever(Protocol):
    """Retrieve the top-k most relevant Chunks for a Query."""

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...

    def name(self) -> str: ...
