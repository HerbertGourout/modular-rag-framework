from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace


@runtime_checkable
class Generator(Protocol):
    """Generate a grounded Answer from a Query and its retrieved context."""

    def generate(
        self,
        query: Query,
        context: list[RetrievedChunk],
        trace: Trace,
    ) -> Answer: ...

    async def agenerate(
        self,
        query: Query,
        context: list[RetrievedChunk],
        trace: Trace,
    ) -> Answer: ...

    def name(self) -> str: ...
