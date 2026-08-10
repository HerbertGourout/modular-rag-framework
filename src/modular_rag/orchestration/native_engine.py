"""NativeEngineAdapter — wraps RAGEngine to conform to the DocumentEngine
port (contracts/engine.py, Lot 7).

This is the "native adapter" per ADR-0005 §5.4/§5.5: a bounded reference
implementation, not the long-term core. It exists so RAGEngine can be
addressed through the same neutral port a future LangGraph adapter (Lot 15,
ADR-0006) will implement — proving the port isn't designed around one
engine's shape.

Declares an empty capability set deliberately: RAGEngine.answer() is a
single synchronous call with no native streaming, cancellation, or
tool-use support, and its own internal SecurityGuard check (wired via the
manifest, raising SecurityError) is a separate, pre-existing mechanism —
not the same thing as this port's `GovernanceHook`. Overclaiming a
capability this adapter can't actually honor would be worse than declaring
none; see docs/architecture/document-engine-contract.md.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from modular_rag import __version__
from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.core.errors import EngineCapabilityError
from modular_rag.orchestration.engine import RAGEngine


class NativeEngineAdapter:
    """`DocumentEngine` adapter over the native V1 `RAGEngine`."""

    def __init__(self, rag_engine: RAGEngine) -> None:
        self._engine = rag_engine

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        return frozenset()

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        # `context.governance_hook`/`cancellation_token` are intentionally not
        # consulted: neither capability is declared, so per the port's own
        # semantics (tests/contract/test_engine_conformance.py) both must be
        # ignored, not silently honored. RAGEngine's own internal guard check
        # still runs as it always has, via the manifest-wired SecurityGuard —
        # a SecurityError from that path propagates to the caller unchanged.
        #
        # `context.tenant_id` IS consulted (Lot 11b, docs/refactoring-plan.md
        # — "Propagate authenticated identity and tenant through
        # ExecutionContext"): it is the authoritative identity source per
        # ExecutionContext's own docstring, forwarded into RAGEngine.answer()
        # so a configured Container.tenant_policy can enforce against it.
        # `str | None` (Lot 1, tenant fail-closed) — a `None` context.tenant_id
        # (no verified identity) is forwarded unchanged, never coerced into a
        # placeholder value; RAGEngine.answer()'s own tenant_policy check
        # denies it when tenant isolation is configured. Note `request.query
        # .tenant_id` is never consulted here — `context.tenant_id` is the
        # sole source, matching LangGraphEngineAdapter's identical rule.
        answer = self._engine.answer(request.query.text, tenant_id=context.tenant_id)
        metadata = {"trace_id": answer.trace_id} if answer.trace_id else {}
        return EngineResult(
            text=answer.text,
            citations=list(answer.citations),
            steps=[],  # RAGEngine builds a Trace internally but doesn't return it (Lot 10 gap)
            metadata=metadata,
        )

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        # RAGEngine has no native async path today; this is a synchronous call
        # wrapped in a coroutine, not real concurrency. Documented, not hidden.
        return self.run(request, context)

    async def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        raise EngineCapabilityError(
            f"{self.name()} does not declare EngineCapability.STREAMING"
        )
        yield  # pragma: no cover - makes this an async generator for type-checking

    def name(self) -> str:
        return "native"

    def engine_version(self) -> str:
        return __version__
