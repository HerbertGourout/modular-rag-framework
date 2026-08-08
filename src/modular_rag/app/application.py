"""Stable application facade used by HTTP and CLI interfaces."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from modular_rag.contracts.engine import EngineRequest, ExecutionContext
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.orchestration.engine import RAGEngine

if TYPE_CHECKING:
    from modular_rag.contracts.chunking import Chunker
    from modular_rag.contracts.engine import DocumentEngine
    from modular_rag.core.models.chunk import Chunk
    from modular_rag.core.models.retrieved import RetrievedChunk


class ApplicationService:
    """Expose application use cases while hiding domains and orchestration."""

    def __init__(self, native: RAGEngine, selected: DocumentEngine) -> None:
        self._native = native
        self._selected = selected

    @property
    def manifest_id(self) -> str:
        return self._native.manifest_id

    @property
    def engine_name(self) -> str:
        """Selected answer-engine name without exposing the adapter object."""
        return self._selected.name()

    @property
    def chunker(self) -> Chunker:
        return self._native.chunker

    def ingest_chunks(self, chunks: list[Chunk]) -> int:
        return self._native.ingest_chunks(chunks)

    def answer(self, question: str, tenant_id: str | None = None) -> Answer:
        request_id = str(uuid.uuid4())
        effective_tenant = tenant_id or "default"
        query = Query(text=question, tenant_id=tenant_id)
        context = ExecutionContext(
            tenant_id=effective_tenant,
            correlation_id=str(uuid.uuid4()),
            request_id=request_id,
        )
        result = self._selected.run(EngineRequest(query=query), context)
        return Answer(
            query_id=query.id,
            text=result.text,
            citations=result.citations,
            trace_id=result.metadata.get("trace_id"),
            metadata={"engine": self._selected.name(), **result.metadata},
        )

    def retrieve(
        self, question: str, k: int = 10, tenant_id: str | None = None
    ) -> list[RetrievedChunk]:
        # Raw retrieval is a native application use case; DocumentEngine owns
        # answer orchestration and deliberately has no retrieval-only method.
        return self._native.retrieve(question, k=k, tenant_id=tenant_id)

    def close(self) -> None:
        """Release every resource owned by the wired application."""
        self._native.close()
