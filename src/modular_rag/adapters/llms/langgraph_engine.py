"""LangGraphEngineAdapter — the second `DocumentEngine` (contracts/engine.py,
Lot 7) implementation, per ADR-0006's selection and Lot 15
(docs/refactoring-plan.md — "Implement the selected external adapter. It
must pass the same semantic engine, governance, audit, migration, quality,
cancellation, and failure tests as native V1. Express differences through
capabilities and documented extension configuration.").

Unlike `NativeEngineAdapter` (Lot 8), which wraps the whole `RAGEngine`,
this adapter orchestrates the *same* wired `Container` components
(retriever, guard, generator, tenant_policy, redactor) directly through a
LangGraph `StateGraph` — proving the port is genuinely engine-neutral by
running identical components through a structurally different
orchestration engine, not by wrapping the native engine a second time
(which would prove nothing about LangGraph's own capabilities).

`langgraph` is lazy-imported (per `.claude/.instructions.md` §4 and
ADR-0006's own risk note: "must stay isolated behind the `DocumentEngine`
port... so it never leaks into core/contracts") — this module is importable
without `langgraph` installed; only `_build_graph()` needs it.

This module lives under `adapters/`, so `scripts/check_layering.py`
restricts its imports to `core` + `contracts` + `adapters` only —
`app.container.Container` (`app/`) is not on that list. Rather than import
the concrete class, `__init__` is typed against `_ComponentSource` below, a
local `Protocol` describing only the subset of `Container` this adapter
actually uses. `Container` satisfies it structurally without either module
importing the other; `orchestration/native_engine.py`'s `NativeEngineAdapter`
sidesteps the same rule differently — by living in the unrestricted
`orchestration/` layer instead — since it wraps the whole `RAGEngine`, not
individual components, and CLAUDE.md's "Adapter Stubs" table names
`adapters/llms/` as this adapter's intended home either way.

Known scope boundary, recorded honestly (Lot 15): this adapter replicates
the *security-critical* governance RAGEngine performs — tenant isolation,
the container's `SecurityGuard`, redaction — since those must hold
regardless of which engine executes a request. It does **not** replicate
`RAGEngine`'s audit-event emission or human-review queueing; duplicating
those inside every engine adapter is the wrong place for them long-term
(they belong above the `DocumentEngine` boundary, in the control plane that
calls whichever adapter is selected — a future architectural refactor, not
this lot's job to invent). A caller relying on audit evidence today should
use `NativeEngineAdapter`/`RAGEngine` directly, or `load_pipeline()`.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Protocol, TypedDict, runtime_checkable

from modular_rag import __version__ as _package_version
from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.contracts.generation import Generator
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.contracts.retrieval import Retriever
from modular_rag.contracts.security import Redactor, SecurityGuard, TenantPolicy
from modular_rag.core.errors import EngineCancelledError, EngineCapabilityError, SecurityError
from modular_rag.core.models.answer import Citation
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace


@runtime_checkable
class _ComponentSource(Protocol):
    """Structural shape this adapter needs from a wired `Container`
    (`app/container.py`) — see the module docstring for why this is a local
    Protocol instead of importing `Container` directly."""

    manifest: PipelineManifest

    @property
    def retriever(self) -> Retriever: ...

    @property
    def generator(self) -> Generator: ...

    @property
    def guard(self) -> SecurityGuard | None: ...

    @property
    def tenant_policy(self) -> TenantPolicy | None: ...

    @property
    def redactor(self) -> Redactor | None: ...


class _GraphState(TypedDict):
    query: Query
    context: ExecutionContext
    chunks: list[RetrievedChunk]
    steps: list[EngineStep]
    blocked_reason: str | None
    answer_text: str | None
    citations: list[Citation]


class LangGraphEngineAdapter:
    """`DocumentEngine` adapter over LangGraph (ADR-0006), orchestrating the
    same `Container` components `RAGEngine`/`NativeEngineAdapter` use."""

    def __init__(self, container: _ComponentSource) -> None:
        self._c = container
        self._graph: Any = None  # compiled lazily — needs langgraph installed

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        # STREAMING: real — LangGraph's own .astream()/.stream() per-node
        # updates, no extra instrumentation needed (the exact reason ADR-0006
        # picked LangGraph — "automatic, zero-instrumentation step-level
        # streaming").
        # GOVERNANCE_INTERCEPT: real — the guard node below consults both
        # Container.guard and context.governance_hook.
        # CANCELLATION: built on asyncio.Task cancellation per ADR-0006's own
        # note that LangGraph has no native cancellation API — this contract
        # is ours to define and test (checked at each node boundary below),
        # not adopted from the underlying engine.
        return frozenset(
            {
                EngineCapability.STREAMING,
                EngineCapability.GOVERNANCE_INTERCEPT,
                EngineCapability.CANCELLATION,
            }
        )

    def name(self) -> str:
        return "langgraph"

    def engine_version(self) -> str:
        try:
            import langgraph

            return getattr(langgraph, "__version__", _package_version)
        except ImportError:
            return _package_version

    # -- graph construction --

    def _get_graph(self) -> Any:
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise ImportError(
                "langgraph is required for LangGraphEngineAdapter. "
                "Install it with: pip install modular-rag[langgraph]"
            ) from exc

        g = StateGraph(_GraphState)
        g.add_node("route", self._node_route)
        g.add_node("retrieve", self._node_retrieve)
        g.add_node("guard", self._node_guard)
        g.add_node("generate", self._node_generate)
        g.add_node("blocked", self._node_blocked)
        g.add_edge(START, "route")
        g.add_edge("route", "retrieve")
        g.add_edge("retrieve", "guard")
        g.add_conditional_edges(
            "guard",
            lambda state: "blocked" if state["blocked_reason"] else "generate",
            {"blocked": "blocked", "generate": "generate"},
        )
        g.add_edge("generate", END)
        g.add_edge("blocked", END)
        return g.compile()

    # -- nodes --
    # Each node checks cancellation at its own boundary (Lot 15/ADR-0006:
    # "must check context.cancellation_token.is_cancelled at every reasonable
    # step boundary" — see docs/architecture/document-engine-contract.md).

    def _check_cancelled(self, context: ExecutionContext, request_id: str) -> None:
        if (
            EngineCapability.CANCELLATION in self.capabilities
            and context.cancellation_token is not None
            and context.cancellation_token.is_cancelled
        ):
            raise EngineCancelledError(f"run {request_id} was cancelled")

    def _node_route(self, state: _GraphState) -> dict[str, Any]:
        t0 = time.perf_counter()
        self._check_cancelled(state["context"], state["context"].request_id)
        ms = (time.perf_counter() - t0) * 1000
        return {"steps": [*state["steps"], EngineStep("route", ms, {})]}

    def _node_retrieve(self, state: _GraphState) -> dict[str, Any]:
        t0 = time.perf_counter()
        self._check_cancelled(state["context"], state["context"].request_id)
        query = state["query"]
        k = self._c.manifest.retriever.config.get("k", 20)
        chunks = self._c.retriever.retrieve(query, k=k)

        tenant_policy = self._c.tenant_policy
        if tenant_policy and query.tenant_id:
            chunks = tenant_policy.filter_chunks(query.tenant_id, chunks)

        ms = (time.perf_counter() - t0) * 1000
        return {
            "chunks": chunks,
            "steps": [*state["steps"], EngineStep("retrieve", ms, {"chunks": len(chunks)})],
        }

    def _node_guard(self, state: _GraphState) -> dict[str, Any]:
        t0 = time.perf_counter()
        self._check_cancelled(state["context"], state["context"].request_id)
        query = state["query"]
        steps = list(state["steps"])

        # Container.guard denial raises immediately, matching RAGEngine/
        # NativeEngineAdapter's own SecurityError convention exactly (Lot 15:
        # "must pass the same governance... tests as native V1" — this is the
        # same mechanism as the native path, not the port-level
        # GovernanceHook below, so it must behave identically to native, not
        # merely similarly).
        guard = self._c.guard
        if guard is not None:
            result = guard.check_query(query)
            if not result.allowed:
                raise SecurityError(result.reason or "Query blocked by security guard.")

        # GovernanceHook (contracts/engine.py) has no equivalent in
        # NativeEngineAdapter to stay consistent with — its "blocked ->
        # EngineResult, not exception" semantics come from the port's own
        # conformance suite (tests/contract/test_engine_conformance.py),
        # which this adapter must also satisfy.
        blocked_reason: str | None = None
        hook = state["context"].governance_hook
        if EngineCapability.GOVERNANCE_INTERCEPT in self.capabilities and hook is not None:
            decision = hook.check("generate", {"query": query.text})
            if not decision.allowed:
                blocked_reason = decision.reason or "Blocked by governance hook."

        ms = (time.perf_counter() - t0) * 1000
        steps.append(EngineStep("guard", ms, {"allowed": blocked_reason is None}))
        return {"steps": steps, "blocked_reason": blocked_reason}

    def _node_blocked(self, state: _GraphState) -> dict[str, Any]:
        reason = state["blocked_reason"]
        return {
            "answer_text": f"Blocked: {reason}",
            "citations": [],
            "steps": [*state["steps"], EngineStep("blocked", 0.0, {"reason": reason})],
        }

    def _node_generate(self, state: _GraphState) -> dict[str, Any]:
        query = state["query"]
        self._check_cancelled(state["context"], state["context"].request_id)
        trace = Trace(query_id=query.id, pipeline_id=self._c.manifest.id)
        answer = self._c.generator.generate(query, state["chunks"], trace)

        guard = self._c.guard
        if guard is not None:
            result = guard.check_answer(answer)
            if not result.allowed:
                raise SecurityError(result.reason or "Answer blocked by security guard.")
            if result.modified_content:
                answer = answer.model_copy(update={"text": result.modified_content})

        redactor = self._c.redactor
        text = redactor.redact(answer.text) if redactor else answer.text

        # Fold the generator's own TraceStep instrumentation into this run's
        # EngineSteps — TraceStep/EngineStep are shape-compatible on purpose
        # (contracts/engine.py's EngineStep docstring).
        generated_steps = [
            EngineStep(s.name, s.latency_ms, dict(s.metadata)) for s in trace.steps
        ]
        return {
            "answer_text": text,
            "citations": list(answer.citations),
            "steps": [*state["steps"], *generated_steps],
        }

    def _initial_state(self, request: EngineRequest, context: ExecutionContext) -> _GraphState:
        query = request.query
        if context.tenant_id and not query.tenant_id:
            query = query.model_copy(update={"tenant_id": context.tenant_id})
        return _GraphState(
            query=query,
            context=context,
            chunks=[],
            steps=[],
            blocked_reason=None,
            answer_text=None,
            citations=[],
        )

    @staticmethod
    def _to_result(state: dict[str, Any]) -> EngineResult:
        return EngineResult(
            text=state["answer_text"] or "",
            citations=state["citations"],
            steps=state["steps"],
        )

    # -- DocumentEngine contract --

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        graph = self._get_graph()
        final_state = graph.invoke(self._initial_state(request, context))
        return self._to_result(final_state)

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        graph = self._get_graph()
        final_state = await graph.ainvoke(self._initial_state(request, context))
        return self._to_result(final_state)

    async def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        if EngineCapability.STREAMING not in self.capabilities:
            raise EngineCapabilityError(
                f"{self.name()} does not declare EngineCapability.STREAMING"
            )
        graph = self._get_graph()
        seen = 0
        async for update in graph.astream(
            self._initial_state(request, context), stream_mode="updates"
        ):
            for node_output in update.values():
                new_steps = node_output.get("steps", [])
                for step in new_steps[seen:]:
                    yield step
                seen = len(new_steps)
