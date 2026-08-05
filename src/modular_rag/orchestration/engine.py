from __future__ import annotations

import time
from typing import Any

import structlog

from modular_rag.app.container import Container
from modular_rag.contracts.audit import AuditEvent, AuditEventType
from modular_rag.contracts.chunking import Chunker
from modular_rag.contracts.retrieval import Retriever
from modular_rag.core.errors import SecurityError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.document import Document
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.orchestration.router import QueryRouter
from modular_rag.orchestration.state_machine import PipelineState, PipelineStateMachine

log = structlog.get_logger(__name__)


class RAGEngine:
    """Main entry point: ingest documents and answer queries via a configured pipeline."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self._router = QueryRouter()

    # -- public API --

    @property
    def manifest_id(self) -> str:
        """Public accessor for the wired pipeline's manifest id. Added in Lot 8
        (docs/refactoring-plan.md) specifically so callers (API, CLI) stop
        reaching into the private `_c` container directly."""
        return self._c.manifest.id

    @property
    def chunker(self) -> Chunker:
        """Public accessor for the wired chunker. Ingestion entry points (CLI,
        API) that parse files from disk need a `Chunker` instance to pass to
        `ingestion.pipelines.default.ingest_path`/`ingest_directory` — this is
        the supported way to get one, instead of `pipeline._c.chunker`."""
        return self._c.chunker

    @property
    def retriever(self) -> Retriever:
        """Public accessor for the wired retriever. Exists for callers that
        need to introspect retrieval behavior directly (e.g.
        examples/hybrid_search/ comparing vector-only vs. BM25-only vs. fused
        results) instead of reaching into `pipeline._c.retriever`."""
        return self._c.retriever

    def ingest(self, documents: list[Document]) -> int:
        """Chunk and index a list of documents. Returns the number of chunks indexed."""
        all_chunks = []
        for doc in documents:
            chunks = self._c.chunker.chunk(doc)
            all_chunks.extend(chunks)
        return self.ingest_chunks(all_chunks)

    def ingest_chunks(self, chunks: list) -> int:
        """Embed and index pre-chunked content. Use when chunks are produced externally.

        Also feeds the BM25 index inside HybridRetriever so lexical retrieval works.
        """
        for chunk in chunks:
            if chunk.embedding is None:
                chunk.embedding = self._c.embedder.embed([chunk.content])[0]
        self._c.indexer.index(chunks)
        # Feed BM25 — covers standalone BM25Retriever and HybridRetriever._bm25
        retriever = self._c.retriever
        for target in [retriever, getattr(retriever, "_bm25", None)]:
            if target is not None and hasattr(target, "index"):
                target.index(chunks)
                break
        log.info("engine.ingested", chunks=len(chunks))
        return len(chunks)

    def answer(self, question: str, **query_kwargs: object) -> Answer:
        """Answer a natural-language question and return a sourced Answer."""
        query = Query(text=question, **query_kwargs)  # type: ignore[arg-type]
        return self._run(query)

    def retrieve(self, question: str, k: int = 10) -> list[RetrievedChunk]:
        """Return raw retrieved chunks without generating an answer."""
        query = Query(text=question)
        return self._retrieve(query, k)

    # -- internal pipeline --

    def _run(self, query: Query) -> Answer:
        trace = Trace(query_id=query.id, pipeline_id=self._c.manifest.id)
        sm = PipelineStateMachine(self._c.manifest.id)
        try:
            ans = self._run_steps(query, trace, sm)
        except Exception as exc:
            # Lot 10 (docs/refactoring-plan.md): a failed run used to skip
            # telemetry entirely — nothing was recorded for a blocked query,
            # a retrieval error, or a generation failure. `trace.failed`/
            # `failure_reason` now capture that a run happened and why it
            # didn't complete, and telemetry still gets the trace, before the
            # original exception propagates unchanged to the caller.
            trace.failed = True
            trace.failure_reason = str(exc)
            if self._c.telemetry:
                self._c.telemetry.record_trace(trace)
            self._audit(
                query,
                trace,
                event_type=AuditEventType.RUN_FAILED,
                payload={"error_type": type(exc).__name__},
            )
            log.warning("engine.failed", query_id=query.id, error=str(exc))
            raise
        if self._c.telemetry:
            self._c.telemetry.record_trace(trace)
        self._audit(
            query,
            trace,
            event_type=AuditEventType.RUN_SUCCEEDED,
            payload={"answer_length": len(ans.text), "citation_count": len(ans.citations)},
        )
        sm.transition(PipelineState.DONE)
        log.info("engine.answered", query_id=query.id, latency_ms=trace.total_latency_ms)
        return ans

    def _audit(
        self, query: Query, trace: Trace, *, event_type: AuditEventType, payload: dict[str, Any]
    ) -> None:
        """Record compliance-audit evidence for one run (Lot 10,
        docs/refactoring-plan.md). No-op unless a Container-registered
        `audit_sink` is present — mirrors `telemetry`'s optionality so
        existing manifests/tests are unaffected. `tenant_id` reads from
        `query.metadata` because `Query` has no dedicated tenant field yet;
        full identity/tenant propagation via `ExecutionContext` is Lot 11b.
        """
        if not self._c.audit_sink:
            return
        event = AuditEvent(
            event_type=event_type,
            correlation_id=trace.id,
            tenant_id=str(query.metadata.get("tenant_id", "unknown")),
            payload=payload,
        )
        self._c.audit_sink.record(event)

    def _run_steps(self, query: Query, trace: Trace, sm: PipelineStateMachine) -> Answer:
        # 1. security guard — query
        if self._c.guard:
            sm.transition(PipelineState.GUARDING_QUERY)
            t0 = time.perf_counter()
            result = self._c.guard.check_query(query)
            trace.add_step(
                TraceStep(name="guard_query", latency_ms=(time.perf_counter() - t0) * 1000)
            )
            if not result.allowed:
                raise SecurityError(result.reason or "Query blocked by security guard.")

        # 2. retrieval
        sm.transition(PipelineState.RETRIEVING)
        context = self._retrieve(query, k=self._c.manifest.retriever.config.get("k", 20))
        trace.add_step(TraceStep(name="retrieve", metadata={"chunks": len(context)}))

        # 3. reranking
        if self._c.reranker and context:
            sm.transition(PipelineState.RERANKING)
            k_rerank = self._c.manifest.retriever.config.get("reranker_k", 5)
            t0 = time.perf_counter()
            context = self._c.reranker.rerank(query, context, k=int(k_rerank))
            trace.add_step(TraceStep(name="rerank", latency_ms=(time.perf_counter() - t0) * 1000))

        # 4. generation
        # No wrapping TraceStep here on purpose (Lot 10, docs/refactoring-plan.md):
        # every registered Generator already calls `trace.add_step(...)` itself
        # inside `generate()` (e.g. "openai_generate" with real token counts) —
        # per the documented pattern in .claude/.instructions.md section 3
        # ("Generation: in generate() method"). Adding a second wrapping step
        # here duplicated the generator's own step under a different name
        # ("generate" vs. e.g. "openai_generate") with an overlapping — not
        # identical — time window, and silently double-counted generation
        # latency into `trace.total_latency_ms`.
        sm.transition(PipelineState.GENERATING)
        ans = self._c.generator.generate(query, context, trace)
        ans = ans.model_copy(update={"trace_id": trace.id})

        # 5. security guard — answer
        if self._c.guard:
            sm.transition(PipelineState.GUARDING_ANSWER)
            result = self._c.guard.check_answer(ans)
            if not result.allowed:
                raise SecurityError(result.reason or "Answer blocked by security guard.")
            if result.modified_content:
                ans = ans.model_copy(update={"text": result.modified_content})

        return ans

    def _retrieve(self, query: Query, k: int) -> list[RetrievedChunk]:
        t0 = time.perf_counter()
        chunks = self._c.retriever.retrieve(query, k=k)
        log.debug("engine.retrieved", chunks=len(chunks), ms=(time.perf_counter() - t0) * 1000)
        return chunks
