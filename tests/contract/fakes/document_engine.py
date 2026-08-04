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

from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.core.errors import EngineCancelledError, EngineCapabilityError
from modular_rag.core.models.answer import Citation


class FakeDocumentEngine:
    """In-memory DocumentEngine. No network, no external engine dependency."""

    def __init__(self, capabilities: frozenset[EngineCapability] | None = None) -> None:
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

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        steps = self._steps(request, context)
        if steps and steps[-1].name == "blocked":
            return EngineResult(
                text=f"Blocked: {steps[-1].metadata.get('reason')}", citations=[], steps=steps
            )
        chunks = request.context_chunks or self._DEFAULT_CHUNKS
        citations = [
            Citation(
                chunk_id=str(c.get("chunk_id", "c1")),
                source=str(c.get("source", "fake-source")),
                passage=str(c.get("content", ""))[:200],
                score=float(c.get("score", 0.0)),
            )
            for c in chunks
        ]
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
