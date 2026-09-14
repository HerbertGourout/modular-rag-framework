"""FakeDocumentEngine — the reference DocumentEngine implementation the
semantic conformance suite (test_engine_conformance.py) is written against.

Not a mock: a real, if trivial, working implementation of the Protocol,
covering the same route -> retrieve -> guard -> generate shape as the Lot 6
spikes (docs/refactoring/lot-6-spike/), so the conformance suite tests
actual behavior rather than call-recording.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from modular_rag.contracts.assurance import (
    ConformanceReport,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    classify_provenance,
)
from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import EngineCancelledError, EngineCapabilityError
from modular_rag.core.models.answer import Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk


class FakeDocumentEngine:
    """In-memory DocumentEngine. No network, no external engine dependency."""

    def __init__(self, capabilities: frozenset[EngineCapability] | None = None) -> None:
        # Lot 21 (Codex review pass 1, HIGH-003): execution-derived provenance,
        # keyed by request id, exactly like both shipped adapters.
        self._execution_evidence: dict[str, EvidenceStatus] = {}
        self._capabilities = (
            capabilities
            if capabilities is not None
            else frozenset(
                {
                    EngineCapability.STREAMING,
                    EngineCapability.CANCELLATION,
                    EngineCapability.GOVERNANCE_INTERCEPT,
                }
            )
        )

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        return self._capabilities

    def name(self) -> str:
        return "fake"

    def engine_version(self) -> str:
        return "0.0.0"

    def _check_cancelled(self, context: ExecutionContext) -> None:
        if (
            EngineCapability.CANCELLATION in self._capabilities
            and context.cancellation_token is not None
            and context.cancellation_token.is_cancelled
        ):
            raise EngineCancelledError(f"run {context.request_id} was cancelled")

    _DEFAULT_CHUNKS = [{"chunk_id": "c1", "content": "fake context", "score": 0.9}]

    def _steps(self, request: EngineRequest, context: ExecutionContext) -> list[EngineStep]:
        steps: list[EngineStep] = []

        t0 = time.perf_counter()
        self._check_cancelled(context)
        ms = (time.perf_counter() - t0) * 1000
        steps.append(EngineStep("route", ms, {"needs_retrieval": True}))

        t0 = time.perf_counter()
        self._check_cancelled(context)
        retrieved = request.context_chunks or self._DEFAULT_CHUNKS
        ms = (time.perf_counter() - t0) * 1000
        steps.append(EngineStep("retrieve", ms, {"chunks": len(retrieved)}))

        hook = context.governance_hook
        if EngineCapability.GOVERNANCE_INTERCEPT in self._capabilities and hook is not None:
            t0 = time.perf_counter()
            decision = hook.check("generate", {"query": request.query.text})
            ms = (time.perf_counter() - t0) * 1000
            steps.append(EngineStep("guard", ms, {"allowed": decision.allowed}))
            if not decision.allowed:
                steps.append(EngineStep("blocked", 0.0, {"reason": decision.reason}))
                return steps

        t0 = time.perf_counter()
        self._check_cancelled(context)
        steps.append(EngineStep("generate", (time.perf_counter() - t0) * 1000, {}))
        return steps

    @staticmethod
    def _as_retrieved(raw: dict) -> RetrievedChunk:
        """`EngineRequest.context_chunks` is a plain dict list by contract, but
        the shared grounding check compares real `Citation`/`RetrievedChunk`
        evidence (Lot 21; Codex review pass 2, HIGH-003). Converting here keeps
        one definition of "grounded" across every engine instead of giving the
        fake a weaker, dict-shaped one of its own."""
        return RetrievedChunk(
            chunk=Chunk(
                id=str(raw.get("chunk_id", "c1")),
                doc_id="fake-doc",
                content=str(raw.get("content", "")),
                page=raw.get("page"),
                metadata={"source": str(raw.get("source", "fake-source"))},
            ),
            score=float(raw.get("score", 0.0)),
            rank=1,
            retrieval_method=RetrievalMethod.HYBRID,
        )

    def build_citations(self, retrieved: list[RetrievedChunk]) -> list[Citation]:
        """The fake's stand-in for a `Generator` — the one component that
        decides what the caller is told was used.

        Split out from `run()` so a subclass can lie here *without* touching
        the framework-owned classification below it, mirroring the real
        engines, where the generator and `classify_provenance()` are separate
        parties. `_FabricatingFakeDocumentEngine` in
        `tests/contract/test_engine_conformance.py` overrides exactly this, so
        the VERIFIED probe exercises this engine's real grounding check rather
        than a hand-computed answer (Codex review pass 2, HIGH-004).
        """
        return [
            Citation(
                chunk_id=hit.chunk.id,
                source=hit.chunk.metadata.get("source", "unknown"),
                passage=hit.chunk.content[:200],
                score=hit.score,
                page=hit.chunk.page,
            )
            for hit in retrieved
        ]

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        # Lot 21 (Codex review pass 2, HIGH-005): clear any evidence this
        # request id already carries before the attempt starts, so a reused id
        # cannot inherit an earlier attempt's provenance.
        self._execution_evidence.pop(context.request_id, None)
        steps = self._steps(request, context)
        if steps and steps[-1].name == "blocked":
            return EngineResult(
                text=f"Blocked: {steps[-1].metadata.get('reason')}", citations=[], steps=steps
            )
        chunks = request.context_chunks or self._DEFAULT_CHUNKS
        retrieved = [self._as_retrieved(c) for c in chunks]
        citations = self.build_citations(retrieved)
        # Same framework-owned grounding check both shipped engines run, via
        # the one shared definition in contracts.assurance (Lot 21, HIGH-003).
        self._execution_evidence[context.request_id] = classify_provenance(citations, retrieved)
        return EngineResult(
            text=f"answer to '{request.query.text}' grounded in {len(chunks)} chunk(s)",
            citations=citations,
            steps=steps,
        )

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        return self.run(request, context)

    async def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        if EngineCapability.STREAMING not in self._capabilities:
            raise EngineCapabilityError(
                f"{self.name()} does not declare EngineCapability.STREAMING"
            )
        for step in self._steps(request, context):
            yield step

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        """Honest baseline report (Lot 21, ADR-0017), corrected after Codex
        review pass 1.

        This fake has no tenant/egress/audit/review/meter concept at all, so
        those kinds are always `UNSUPPORTED`. `POLICY_DECISION`/
        `STREAMING_PREVALIDATION` reflect the *same* real check `_steps()`
        performs (a governance-hook denial genuinely stops "generate" from
        running). `RETRIEVAL_PROVENANCE` is execution-derived, exactly like
        both shipped adapters (HIGH-003): an earlier version claimed
        `VERIFIED` unconditionally, which is an overclaim for any request that
        has not run — and this fake is the reference every adapter author
        reads, so it must model the honest pattern rather than the convenient
        one.

        Subclassed by `_OverclaimingFakeDocumentEngine` in
        `tests/contract/test_engine_conformance.py`, which deliberately
        breaks this honesty so the shared behavioural harness can prove it
        catches a report that does not match real behaviour.
        """
        hook_enforced = (
            EngineCapability.GOVERNANCE_INTERCEPT in self._capabilities
            and context.governance_hook is not None
        )
        streaming_declared = EngineCapability.STREAMING in self._capabilities
        evidence = (
            EvidenceEntry(EvidenceKind.IDENTITY_TENANT, EvidenceStatus.UNSUPPORTED),
            EvidenceEntry(
                EvidenceKind.RETRIEVAL_PROVENANCE,
                self._execution_evidence.get(
                    context.request_id, EvidenceStatus.UNSUPPORTED
                ),
            ),
            EvidenceEntry(EvidenceKind.EGRESS_DECISION, EvidenceStatus.UNSUPPORTED),
            EvidenceEntry(
                EvidenceKind.POLICY_DECISION,
                EvidenceStatus.ENFORCED if hook_enforced else EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(EvidenceKind.AUDIT_COMPLETION, EvidenceStatus.UNSUPPORTED),
            EvidenceEntry(EvidenceKind.USAGE_COST, EvidenceStatus.UNSUPPORTED),
            EvidenceEntry(EvidenceKind.FEEDBACK_REVIEW_ROUTING, EvidenceStatus.UNSUPPORTED),
            EvidenceEntry(
                EvidenceKind.STREAMING_PREVALIDATION,
                # Codex review pass 1, MEDIUM-001: no pre-output check runs
                # when no hook is supplied, so claiming OBSERVED from the mere
                # presence of the STREAMING capability was an observation that
                # never happened.
                EvidenceStatus.ENFORCED
                if streaming_declared and hook_enforced
                else EvidenceStatus.UNSUPPORTED,
            ),
        )
        return ConformanceReport(
            adapter_name=self.name(), adapter_version=self.engine_version(), evidence=evidence
        )
