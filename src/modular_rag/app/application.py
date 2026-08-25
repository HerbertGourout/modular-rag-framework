"""Stable application facade used by HTTP and CLI interfaces."""

from __future__ import annotations

import uuid
from contextlib import AbstractContextManager, nullcontext
from typing import TYPE_CHECKING

from modular_rag.contracts.engine import EngineRequest, ExecutionContext
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.orchestration.engine import RAGEngine

if TYPE_CHECKING:
    from modular_rag.contracts.chunking import Chunker
    from modular_rag.contracts.engine import DocumentEngine
    from modular_rag.contracts.reconciliation import ReconciliationReport, RepairResult
    from modular_rag.contracts.tracing import Span, Tracer
    from modular_rag.core.models.chunk import Chunk
    from modular_rag.core.models.health import ReadinessReport
    from modular_rag.core.models.retrieval_result import RetrievalResult


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
    def tracer(self) -> Tracer | None:
        """ADR-0012 — public accessor for the wired tracer, same pattern as
        `chunker` above. `None` when no `observability.tracer` is
        configured; `api/__init__.py` uses this to attach its own
        HTTP-layer span (nested, via OpenTelemetry's own context
        propagation, under the same trace this class's `answer()`/
        `retrieve()` start)."""
        return self._native.tracer

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
        correlation_id = str(uuid.uuid4())
        query = Query(text=question, tenant_id=tenant_id)
        context = ExecutionContext(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            request_id=request_id,
            user_id=user_id,
            roles=roles,
        )
        # ADR-0012: the root span for a request's distributed trace — named
        # "app.request" (not "rag.answer") so it stays distinguishable from
        # `RAGEngine._run()`'s own "rag.answer" span, which nests under this
        # one automatically via OpenTelemetry's own context propagation
        # (same Container-registered `Tracer` instance — no manual id
        # threading into `RAGEngine` required). `correlation_id`/
        # `request_id` are attached as attributes here (propagated, per the
        # task's own requirement) rather than unified into OpenTelemetry's
        # own trace_id — see ADR-0012's explicit out-of-scope note on why
        # those stay separate concepts.
        with self._request_span(
            "answer", correlation_id, request_id, {"engine": self._selected.name()}
        ) as span:
            try:
                result = self._selected.run(EngineRequest(query=query), context)
            except Exception as exc:
                if span is not None:
                    span.record_error(type(exc).__name__)
                raise
            answer_trace_id = result.metadata.get("trace_id")
            if span is not None:
                if isinstance(answer_trace_id, str):
                    span.set_attribute("app.trace_id", answer_trace_id)
                span.set_attribute("status", "ok")
        return Answer(
            query_id=query.id,
            text=result.text,
            citations=result.citations,
            trace_id=answer_trace_id,
            metadata={"engine": self._selected.name(), **result.metadata},
        )

    def retrieve(
        self, question: str, k: int = 10, tenant_id: str | None = None
    ) -> RetrievalResult:
        """Retrieve raw chunks through the native pipeline (no `DocumentEngine`
        dispatch — see the module-level note above), paired with a real
        framework trace_id.

        Codex review pass 1 (HIGH-002): an earlier version of this method
        propagated no `correlation_id`/`request_id` and created no
        application-layer span at all, unlike `answer()` — fixed by giving
        `retrieve()` the same `"app.request"` span treatment as `answer()`.

        Codex review pass 2 (HIGH-002, reopened): that same fix deliberately
        omitted `app.trace_id`, reasoning that `RAGEngine.retrieve()` built
        no `Trace` object to take an id from — but that silently narrowed
        the original "propagate correlation_id, request_id, and trace_id"
        acceptance criterion without an explicit decision to do so. Per an
        explicit human decision, `RAGEngine.retrieve()` now builds a real,
        minimal `Trace` and returns it as `RetrievalResult.trace_id` — this
        method's return type changed from `list[RetrievedChunk]` accordingly
        (a public contract change; see `api/__init__.py`'s `/retrieve` route
        and `docs/api/rest.md` for the resulting response-shape change).
        """
        request_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        with self._request_span("retrieve", correlation_id, request_id) as span:
            try:
                result = self._native.retrieve(question, k=k, tenant_id=tenant_id)
            except Exception as exc:
                if span is not None:
                    span.record_error(type(exc).__name__)
                raise
            if span is not None:
                span.set_attribute("app.trace_id", result.trace_id)
                span.set_attribute("status", "ok")
        return result

    def _request_span(
        self,
        operation: str,
        correlation_id: str,
        request_id: str,
        extra_attributes: dict[str, str] | None = None,
    ) -> AbstractContextManager[Span | None]:
        """Shared `"app.request"` root-span helper for `answer()`/`retrieve()`
        (ADR-0012, extracted during the HIGH-002 corrective batch so both
        methods propagate `correlation_id`/`request_id` identically instead
        of only `answer()` doing so). `None` tracer -> `nullcontext()`,
        matching every other optional-component guard in this codebase."""
        tracer = self.tracer
        if tracer is None:
            return nullcontext()
        attributes: dict[str, str | int | float | bool] = {
            "correlation_id": correlation_id,
            "request_id": request_id,
            "operation": operation,
        }
        if extra_attributes:
            attributes.update(extra_attributes)
        return tracer.start_span("app.request", attributes)

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

    def check_index_reconciliation(self) -> ReconciliationReport:
        """ADR-0011 — one-line delegation, same pattern as `check_readiness()`
        above."""
        return self._native.check_index_reconciliation()

    def repair_index_reconciliation(self, report: ReconciliationReport) -> RepairResult:
        """See `check_index_reconciliation()`."""
        return self._native.repair_index_reconciliation(report)
