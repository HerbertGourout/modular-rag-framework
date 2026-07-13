from __future__ import annotations

import time

import structlog

from modular_rag.app.container import Container
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
        sm.transition(PipelineState.GENERATING)
        t0 = time.perf_counter()
        ans = self._c.generator.generate(query, context, trace)
        trace.add_step(TraceStep(name="generate", latency_ms=(time.perf_counter() - t0) * 1000))
        ans = ans.model_copy(update={"trace_id": trace.id})

        # 5. security guard — answer
        if self._c.guard:
            sm.transition(PipelineState.GUARDING_ANSWER)
            result = self._c.guard.check_answer(ans)
            if not result.allowed:
                raise SecurityError(result.reason or "Answer blocked by security guard.")
            if result.modified_content:
                ans = ans.model_copy(update={"text": result.modified_content})

        # 6. telemetry
        if self._c.telemetry:
            self._c.telemetry.record_trace(trace)

        sm.transition(PipelineState.DONE)
        log.info("engine.answered", query_id=query.id, latency_ms=trace.total_latency_ms)
        return ans

    def _retrieve(self, query: Query, k: int) -> list[RetrievedChunk]:
        t0 = time.perf_counter()
        chunks = self._c.retriever.retrieve(query, k=k)
        log.debug("engine.retrieved", chunks=len(chunks), ms=(time.perf_counter() - t0) * 1000)
        return chunks
