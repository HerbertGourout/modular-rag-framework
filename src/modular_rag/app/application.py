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
    from modular_rag.core.models.health import ReadinessReport
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

    @property
    def requires_identity(self) -> bool:
        """True when the wired pipeline enforces tenant isolation. A caller
        that exposes this service over a network boundary (e.g.
        `api/__init__.py::create_app()`) must refuse to start without an
        authentication mechanism in that case — silently serving a
        tenant-isolated pipeline to unauthenticated callers is exactly the
        fail-open failure mode Lot 1 closes."""
        return self._native.tenant_policy_active

    def ingest_chunks(self, chunks: list[Chunk]) -> int:
        return self._native.ingest_chunks(chunks)

    def answer(
        self,
        question: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        roles: frozenset[str] = frozenset(),
    ) -> Answer:
        """Answer a question through the selected `DocumentEngine`.

        `tenant_id`/`user_id`/`roles` come from a verified identity (API:
        the authenticated `TenantContext`; CLI: the operator-supplied
        `--tenant-id`) or are `None`/empty when there is none — never
        fabricated into a placeholder value (Lot 1, tenant fail-closed:
        this used to coerce a missing `tenant_id` into `"default"`, which
        defeated `TenantIsolationPolicy.enforce_query()`'s fail-closed check
        downstream, since `"default"` is a non-empty, truthy string)."""
        request_id = str(uuid.uuid4())
        query = Query(text=question, tenant_id=tenant_id)
        context = ExecutionContext(
            tenant_id=tenant_id,
            correlation_id=str(uuid.uuid4()),
            request_id=request_id,
            user_id=user_id,
            roles=roles,
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

    def check_readiness(self) -> ReadinessReport:
        """Lot 6 (readiness and resilience) — one-line delegation, same
        pattern as `close()` above. Always goes through `self._native`
        (the native `RAGEngine`/`Container`) regardless of which
        `DocumentEngine` is selected for `answer()`: both adapters wrap the
        identical wired `Container`, and readiness is about the underlying
        external dependencies (Qdrant, PostgreSQL), not about which engine
        orchestrates a query."""
        return self._native.check_readiness()
