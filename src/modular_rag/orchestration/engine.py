from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

import structlog

from modular_rag.app.container import Container
from modular_rag.contracts.audit import AuditEvent, AuditEventType
from modular_rag.contracts.chunking import Chunker
from modular_rag.contracts.erasure import ErasureProof
from modular_rag.contracts.lifecycle import DocumentStatus
from modular_rag.contracts.retrieval import Retriever
from modular_rag.contracts.review import ReviewItem
from modular_rag.core.errors import ConfigurationError, SecurityError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.document import Document
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.ingestion.lifecycle.hashing import content_hash, document_key
from modular_rag.orchestration.state_machine import PipelineState, PipelineStateMachine

log = structlog.get_logger(__name__)


class RAGEngine:
    """Main entry point: ingest documents and answer queries via a configured pipeline."""

    def __init__(self, container: Container) -> None:
        self._c = container

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
        """Chunk and index a list of documents. Returns the number of chunks indexed.

        When a `lifecycle_ledger` is configured (Lot 12a, docs/refactoring-plan.md),
        this becomes idempotent per document: re-ingesting a document whose
        `(tenant_id, source)` key and content hash both match the ledger's
        current record is a no-op (skipped entirely — no re-chunk, re-embed,
        or re-index). Re-ingesting with the same key but *different* content
        is treated as an update: the previous version's chunks are deleted
        (via `_delete_chunk_ids`, covering both the vector index and the
        retriever's lexical index) before the new chunks are indexed, and the
        ledger record is versioned forward. Without a `lifecycle_ledger`,
        behavior is unchanged from before this lot — always re-chunk and
        re-index, no dedup/update tracking.
        """
        ledger = self._c.lifecycle_ledger
        total = 0
        for doc in documents:
            key = document_key(doc.source, doc.tenant_id) if ledger else None
            if ledger and key is not None:
                current_hash = content_hash(doc.content)
                existing = ledger.get(key)
                if (
                    existing is not None
                    and existing.status == DocumentStatus.ACTIVE
                    and existing.content_hash == current_hash
                ):
                    log.debug("engine.ingest_skipped_unchanged", document_key=key)
                    continue
                if existing is not None and existing.chunk_ids:
                    self._delete_chunk_ids(existing.chunk_ids)
            chunks = self._c.chunker.chunk(doc)
            total += self.ingest_chunks(chunks)
            if ledger and key is not None:
                ledger.record_ingested(
                    key, doc.tenant_id, content_hash(doc.content), [c.id for c in chunks]
                )
        return total

    def delete_document(self, document_key: str) -> int:
        """Delete a document (by its `lifecycle_ledger` key) and tombstone its
        ledger record. Idempotent: deleting an already-tombstoned or unknown
        key returns 0 without error. Requires a configured `lifecycle_ledger`
        — raises `ConfigurationError` otherwise, since without one there is no
        record of which chunk ids belong to this document to delete (Lot 12a,
        docs/refactoring-plan.md — closes the gap named in §2's 'Data
        deletion/update' row: previously `RAGEngine` had no `delete()` at
        all)."""
        ledger = self._c.lifecycle_ledger
        if ledger is None:
            raise ConfigurationError(
                "delete_document() requires a configured Container.lifecycle_ledger."
            )
        record = ledger.get(document_key)
        if record is None or record.status == DocumentStatus.TOMBSTONED:
            return 0
        self._delete_chunk_ids(record.chunk_ids)
        ledger.tombstone(document_key)
        log.info("engine.deleted_document", document_key=document_key, chunks=len(record.chunk_ids))
        return len(record.chunk_ids)

    def rebuild_document(self, document: Document) -> int:
        """Force a full re-chunk/re-embed/re-index of `document`, bypassing
        `ingest()`'s idempotency skip. Used to repair a document whose
        indexed state has drifted from what `lifecycle_ledger` expects —
        e.g. to resolve `orchestration.reconciliation.IndexReconciler`'s
        `RepairResult.unresolved_missing` (Lot 12b), which cannot be
        auto-repaired without the original document content (Lot 12c,
        docs/refactoring-plan.md — "rebuild-from-source"). Requires a
        configured `lifecycle_ledger` — raises `ConfigurationError`
        otherwise, since without one there is no record to heal.
        """
        ledger = self._c.lifecycle_ledger
        if ledger is None:
            raise ConfigurationError(
                "rebuild_document() requires a configured Container.lifecycle_ledger."
            )
        key = document_key(document.source, document.tenant_id)
        existing = ledger.get(key)
        if existing is not None and existing.chunk_ids:
            self._delete_chunk_ids(existing.chunk_ids)
        chunks = self._c.chunker.chunk(document)
        n = self.ingest_chunks(chunks)
        ledger.record_ingested(
            key, document.tenant_id, content_hash(document.content), [c.id for c in chunks]
        )
        log.info("engine.rebuilt_document", document_key=key, chunks=n)
        return n

    def erase_document(self, document_key: str) -> ErasureProof:
        """Delete a document and return verifiable proof of erasure (Lot 12c,
        docs/refactoring-plan.md — "right-to-erasure proof"). Unlike
        `delete_document()` (Lot 12a), this re-checks each store's
        `list_ids()` *after* deletion to confirm the removed ids are
        actually gone — proof, not just trust that the `delete()` calls
        didn't raise. Requires a configured `lifecycle_ledger`, same as
        `delete_document()`.
        """
        ledger = self._c.lifecycle_ledger
        if ledger is None:
            raise ConfigurationError(
                "erase_document() requires a configured Container.lifecycle_ledger."
            )
        record = ledger.get(document_key)
        chunk_ids = (
            list(record.chunk_ids)
            if record is not None and record.status == DocumentStatus.ACTIVE
            else []
        )
        self.delete_document(document_key)

        verified_vector = not (set(chunk_ids) & set(self._c.indexer.list_ids()))
        retriever = self._c.retriever
        verified_lexical: bool | None = None
        if hasattr(retriever, "list_ids"):
            verified_lexical = not (set(chunk_ids) & set(retriever.list_ids()))

        tombstoned_at = datetime.now(UTC)
        proof_hash = hashlib.sha256(
            f"{document_key}:{sorted(chunk_ids)}:{tombstoned_at.isoformat()}".encode()
        ).hexdigest()
        proof = ErasureProof(
            document_key=document_key,
            chunk_ids_removed=chunk_ids,
            verified_absent_from_vector=verified_vector,
            verified_absent_from_lexical=verified_lexical,
            tombstoned_at=tombstoned_at,
            proof_hash=proof_hash,
        )
        log.info(
            "engine.erasure_proof",
            document_key=document_key,
            verified_vector=verified_vector,
            verified_lexical=verified_lexical,
        )
        return proof

    def _delete_chunk_ids(self, ids: list[str]) -> None:
        """Coordinate deletion across both the vector/persistent index and the
        retriever's own lexical state — the exact coordination gap Lot 4
        found ("no coordination mechanism to even build on yet")."""
        if not ids:
            return
        self._c.indexer.delete(ids)
        retriever = self._c.retriever
        if hasattr(retriever, "delete"):
            retriever.delete(ids)

    def ingest_chunks(self, chunks: list) -> int:
        """Embed and index pre-chunked content. Use when chunks are produced externally.

        Also feeds the BM25 index inside HybridRetriever so lexical retrieval works.
        """
        if self._c.tenant_policy:
            # Lot 11b (docs/refactoring-plan.md): "enforce fail-closed policy before
            # indexing" — checked before any embedding/indexing work starts, not after.
            for chunk in chunks:
                self._c.tenant_policy.enforce_ingest(chunk.tenant_id)
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

    def retrieve(
        self, question: str, k: int = 10, tenant_id: str | None = None
    ) -> list[RetrievedChunk]:
        """Return raw retrieved chunks without generating an answer.

        Applies the same tenant-isolation enforcement/filtering `answer()`
        does (Lot 16a, docs/refactoring-plan.md — found while wiring API
        auth to this method). Previously `retrieve()` built a `Query` with
        no `tenant_id` and never consulted `Container.tenant_policy` at
        all, so a caller could retrieve any tenant's chunks through this
        method even on a pipeline where `answer()` correctly denied/filtered
        the identical request.
        """
        query = Query(text=question, tenant_id=tenant_id)
        if self._c.tenant_policy:
            self._c.tenant_policy.enforce_query(query)
        chunks = self._retrieve(query, k)
        if self._c.tenant_policy:
            chunks = self._c.tenant_policy.filter_chunks(query.tenant_id, chunks)  # type: ignore[arg-type]
        return chunks

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
        """Record compliance-audit evidence for one run or one governance
        decision (Lot 10/11c, docs/refactoring-plan.md). No-op unless a
        Container-registered `audit_sink` is present — mirrors `telemetry`'s
        optionality so existing manifests/tests are unaffected.

        When a `redactor` is configured, `query_text_redacted` is added to
        the payload — redaction applied *before* the text ever reaches audit
        storage (Lot 11c: "apply configured redaction before storage").
        Omitted entirely (not included unredacted) when no redactor is
        configured, per the allowlist's own safety intent.
        """
        if not self._c.audit_sink:
            return
        if self._c.redactor:
            payload = {**payload, "query_text_redacted": self._c.redactor.redact(query.text)}
        event = AuditEvent(
            event_type=event_type,
            correlation_id=trace.id,
            tenant_id=query.tenant_id or "unknown",
            payload=payload,
        )
        self._c.audit_sink.record(event)

    def _run_steps(self, query: Query, trace: Trace, sm: PipelineStateMachine) -> Answer:
        # 0. tenant isolation — identity check (Lot 11b, docs/refactoring-plan.md).
        # Caught only to record audit evidence of the specific denial (Lot 11c:
        # "emit audit evidence for every governed execution"), then always
        # re-raised unchanged — this is not exception-swallowing. Fail-closed is
        # preserved because the `raise` below is unconditional.
        if self._c.tenant_policy:
            # Not a PipelineStateMachine transition: PipelineState has no dedicated
            # tenant-check state, and this must run before GUARDING_QUERY's own
            # transition below fires.
            try:
                self._c.tenant_policy.enforce_query(query)
            except Exception as exc:
                self._audit(
                    query,
                    trace,
                    event_type=AuditEventType.GUARD_DECISION,
                    payload={"guard_decision": "denied", "error_type": type(exc).__name__},
                )
                raise

        # 1. security guard — query
        if self._c.guard:
            sm.transition(PipelineState.GUARDING_QUERY)
            t0 = time.perf_counter()
            result = self._c.guard.check_query(query)
            trace.add_step(
                TraceStep(name="guard_query", latency_ms=(time.perf_counter() - t0) * 1000)
            )
            if not result.allowed:
                self._audit(
                    query,
                    trace,
                    event_type=AuditEventType.GUARD_DECISION,
                    payload={"guard_decision": "denied", "guard_reason": result.reason or ""},
                )
                raise SecurityError(result.reason or "Query blocked by security guard.")

        # 2. retrieval
        sm.transition(PipelineState.RETRIEVING)
        context = self._retrieve(query, k=self._c.manifest.retriever.config.get("k", 20))
        trace.add_step(TraceStep(name="retrieve", metadata={"chunks": len(context)}))

        # 2b. tenant isolation — filter retrieved context (Lot 11b). `query.tenant_id`
        # is guaranteed set here: step 0 already denied the run otherwise.
        if self._c.tenant_policy:
            before = len(context)
            context = self._c.tenant_policy.filter_chunks(query.tenant_id, context)  # type: ignore[arg-type]
            trace.add_step(
                TraceStep(
                    name="tenant_filter",
                    metadata={"chunks_before": before, "chunks_after": len(context)},
                )
            )

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
                self._audit(
                    query,
                    trace,
                    event_type=AuditEventType.GUARD_DECISION,
                    payload={"guard_decision": "denied", "guard_reason": result.reason or ""},
                )
                raise SecurityError(result.reason or "Answer blocked by security guard.")
            if result.modified_content:
                ans = ans.model_copy(update={"text": result.modified_content})

        # 6. redaction — apply before the answer is returned to the caller (Lot 11c:
        # "apply configured redaction before storage, logging, and external calls").
        # No-op unless a `redactor` is configured, matching every other optional step.
        if self._c.redactor:
            ans = ans.model_copy(update={"text": self._c.redactor.redact(ans.text)})

        # 7. human review — flag high-risk outcomes (Lot 11c). No-op unless a
        # `review_queue` is configured. See security/policies/human_review.py's
        # own docstring for the current, honest limits of what triggers this today.
        if self._c.review_queue and self._c.review_queue.should_review(ans):
            ans = ans.model_copy(update={"metadata": {**ans.metadata, "requires_review": True}})
            self._c.review_queue.enqueue(
                ReviewItem(
                    answer_id=ans.id,
                    query_id=query.id,
                    tenant_id=query.tenant_id,
                    reason="low confidence",
                    confidence=ans.confidence,
                )
            )
            self._audit(
                query,
                trace,
                event_type=AuditEventType.GUARD_DECISION,
                payload={"guard_decision": "flagged_for_review"},
            )

        return ans

    def _retrieve(self, query: Query, k: int) -> list[RetrievedChunk]:
        t0 = time.perf_counter()
        chunks = self._c.retriever.retrieve(query, k=k)
        log.debug("engine.retrieved", chunks=len(chunks), ms=(time.perf_counter() - t0) * 1000)
        return chunks
