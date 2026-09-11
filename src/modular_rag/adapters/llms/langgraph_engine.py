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
from modular_rag.contracts.assurance import (
    ConformanceReport,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    classify_provenance,
)
from modular_rag.contracts.egress import EgressOperation, EgressPolicy
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
from modular_rag.core.enums import combined_classification
from modular_rag.core.errors import (
    EgressDeniedError,
    EngineCancelledError,
    EngineCapabilityError,
    SecurityError,
)
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

    @property
    def egress_policy(self) -> EgressPolicy | None: ...


# Lot 21 (Codex review pass 1, HIGH-003): bounded per-request execution
# evidence, same rationale and capacity as `RAGEngine`'s own store — small on
# purpose, since this is evidence for a recent request rather than an audit
# log, and an unbounded dict keyed by request id would leak.
_EXECUTION_EVIDENCE_CAPACITY = 32


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
        self._execution_evidence: dict[str, dict[EvidenceKind, EvidenceStatus]] = {}

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

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        """Lot 21 (ADR-0017, Accepted 2026-09-10). Unlike `NativeEngineAdapter`
        (a one-line delegation to `RAGEngine`), this adapter has no wrapped
        engine to delegate to: it computes evidence directly from `self._c`'s
        wired roles plus what it recorded while actually serving
        `context.request_id`.

        Same two-source discipline `RAGEngine.conformance_report()` documents,
        for the same Codex review pass 1 reasons:

        - A wired role counts only when it also satisfies its contract
          Protocol (HIGH-002) -- a plain `object()` is not a tenant policy.
        - `RETRIEVAL_PROVENANCE` is execution-derived only (HIGH-003), via the
          shared `contracts.assurance.classify_provenance()`, so one
          definition of "grounded" applies to both shipped engines.
        - Everything this adapter genuinely cannot do reports `UNSUPPORTED`
          rather than a softer-sounding status it has not earned.

        `context.governance_hook` genuinely matters here, unlike native: a
        caller that supplies one, when `GOVERNANCE_INTERCEPT` is declared,
        gets `POLICY_DECISION: ENFORCED` even with no `Container.guard`
        wired -- a real, per-request difference `orchestration/registry.py`'s
        manifest-only pre-flight check cannot see, which is why that check is
        a conservative floor rather than a duplicate of this method.
        """
        capabilities = self.capabilities
        executed = self._execution_evidence.get(context.request_id, {})
        guard_usable = isinstance(self._c.guard, SecurityGuard)
        hook_enforced = (
            EngineCapability.GOVERNANCE_INTERCEPT in capabilities
            and context.governance_hook is not None
        )
        egress_usable = isinstance(self._c.egress_policy, EgressPolicy)
        streaming_declared = EngineCapability.STREAMING in capabilities
        evidence = (
            EvidenceEntry(
                EvidenceKind.IDENTITY_TENANT,
                # _node_retrieve() calls tenant_policy.enforce_query(), raising
                # before retrieval -- the identical fail-closed mechanism
                # RAGEngine uses (Lot 18 parity fix).
                EvidenceStatus.ENFORCED
                if isinstance(self._c.tenant_policy, TenantPolicy)
                else EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.RETRIEVAL_PROVENANCE,
                # Execution-derived only (HIGH-003), recorded by
                # _node_generate() -- never inferred from the fact that a
                # Generator is wired, since contracts.generation.Generator
                # requires nothing about citations.
                executed.get(EvidenceKind.RETRIEVAL_PROVENANCE, EvidenceStatus.UNSUPPORTED),
            ),
            EvidenceEntry(
                EvidenceKind.EGRESS_DECISION,
                # _node_retrieve()/_node_generate() both raise EgressDeniedError
                # before their guarded call (Lot 20, HIGH-002 fix). This graph
                # has no rerank node at all, but EMBED+GENERATE alone already
                # make the checkpoint real.
                EvidenceStatus.ENFORCED if egress_usable else EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.POLICY_DECISION,
                # _node_guard() raises SecurityError on a Container.guard
                # denial (native's own convention, Lot 15), or blocks via the
                # port-level GovernanceHook when the caller supplies one.
                # policy_engine never applies here: it is structurally rejected
                # at wire() for this adapter.
                EvidenceStatus.ENFORCED
                if (guard_usable or hook_enforced)
                else EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.AUDIT_COMPLETION,
                # This adapter's own documented Lot 15 scope boundary (module
                # docstring): it does not replicate RAGEngine's audit-event
                # emission, and governance.audit_sink is structurally rejected
                # under engine.adapter='langgraph'. No wiring changes this.
                # Restates Lot 20's MEDIUM-001 deferral as a machine-readable
                # fact rather than only a prose caveat.
                EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.USAGE_COST,
                # Codex review pass 1, MEDIUM-001: an earlier version reported
                # OBSERVED whenever a Meter was wired. That was false --
                # `mrag.generation.tokens`/`cost_usd` are emitted only inside
                # RAGEngine._run_steps(), which this adapter never calls, so a
                # wired Meter receives no token or cost data from this engine
                # at all. app/application.py's request duration/error metrics
                # are engine-neutral and are not usage/cost evidence.
                EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.FEEDBACK_REVIEW_ROUTING,
                # governance.review_queue/feedback_sink are both structurally
                # rejected under engine.adapter='langgraph' -- same ADR-0008
                # boundary as audit_sink above.
                EvidenceStatus.UNSUPPORTED,
            ),
            EvidenceEntry(
                EvidenceKind.STREAMING_PREVALIDATION,
                # The fixed graph (route -> retrieve -> guard ->
                # [blocked | generate]) structurally runs guard/egress before
                # any streamable "generate" output exists, and astream() only
                # yields a node's steps once that node completes. That ordering
                # is evidence only when something is actually wired to check at
                # that point: with neither a guard nor an egress policy, no
                # pre-output check runs, so this is UNSUPPORTED, not the
                # OBSERVED an earlier version reported (Codex review pass 1,
                # MEDIUM-001 -- the evidence kind requires a check to run).
                EvidenceStatus.ENFORCED
                if streaming_declared and (guard_usable or egress_usable)
                else EvidenceStatus.UNSUPPORTED,
            ),
        )
        return ConformanceReport(
            adapter_name=self.name(), adapter_version=self.engine_version(), evidence=evidence
        )

    def _record_execution_evidence(
        self, context: ExecutionContext, chunks: list[RetrievedChunk], citations: list[Citation]
    ) -> None:
        """Record what this adapter actually verified for one completed
        execution (Lot 21; Codex review pass 1, HIGH-003).

        Mirrors `RAGEngine._record_execution_evidence()`, including its bounded
        store and its refusal to attribute evidence to a request that did not
        produce it. `classify_provenance()` is shared with the native engine so
        "grounded" means exactly one thing across both.
        """
        self._execution_evidence[context.request_id] = {
            EvidenceKind.RETRIEVAL_PROVENANCE: classify_provenance(citations, chunks),
        }
        while len(self._execution_evidence) > _EXECUTION_EVIDENCE_CAPACITY:
            self._execution_evidence.pop(next(iter(self._execution_evidence)))

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

        # Tenant isolation — identity check (Lot 11b), same fail-closed enforcement
        # RAGEngine._run_steps() performs before retrieval. Found missing here via
        # Lot 18's pilot-comparison script: a query with no tenant_id sailed through
        # this adapter to a 200 while the identical request correctly raised
        # SecurityError on native — this node previously only *filtered* chunks
        # when query.tenant_id happened to be set, and never denied the ones where
        # it wasn't. tenant_policy.enforce_query() raises PolicyViolationError
        # (a SecurityError) for the identical reason Container.guard denial does
        # below, so it propagates through _node_guard's raise-through path.
        tenant_policy = self._c.tenant_policy
        if tenant_policy:
            tenant_policy.enforce_query(query)

        # Egress policy (Lot 20, Codex review pass 1, HIGH-002): the retriever embeds the
        # query text internally before returning -- same missing checkpoint, same fix, as
        # RAGEngine._retrieve() on the native path. Query carries no classification field,
        # so this resolves through the policy's own default_classification.
        egress_policy = self._c.egress_policy
        if egress_policy is not None:
            decision = egress_policy.check(
                classification=None,
                provider=self._c.manifest.embedder.type,
                operation=EgressOperation.EMBED,
            )
            if not decision.allowed:
                raise EgressDeniedError(
                    f"{decision.operation.value} denied by egress policy: {decision.reason} "
                    f"(provider={decision.provider!r})"
                )

        k = self._c.manifest.retriever.config.get("k", 20)
        chunks = self._c.retriever.retrieve(query, k=k)

        if tenant_policy:
            # enforce_query() above already raised if query.tenant_id were
            # falsy, so it is guaranteed non-None here — narrows the type
            # instead of masking it with `# type: ignore[arg-type]`.
            assert query.tenant_id is not None
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

        # Egress policy (Lot 20, docs/refactoring-plan.md): the security-critical checkpoint
        # this adapter's own module docstring says it must replicate ("must hold regardless
        # of which engine executes a request"). Uses the same Container.egress_policy/
        # manifest.generator.type inputs RAGEngine._run_steps() checks before its own
        # generate() call -- both engines delegate to the identical wired Generator, so this
        # is "protect delegated engine requests before DocumentEngine.execute()" applied at
        # the actual external-provider call site, not a second, coarser gate around the
        # whole graph run (which would duplicate this same decision for no additional
        # protection, since generation is the only owned external-provider call this graph
        # makes -- retrieval's embedding call is native-only, see ingest_chunks(); this graph
        # has no ingestion node).
        egress_policy = self._c.egress_policy
        if egress_policy is not None:
            decision = egress_policy.check(
                classification=combined_classification(
                    c.chunk.classification for c in state["chunks"]
                ),
                provider=self._c.manifest.generator.type,
                operation=EgressOperation.GENERATE,
            )
            if not decision.allowed:
                raise EgressDeniedError(
                    f"{decision.operation.value} denied by egress policy: {decision.reason} "
                    f"(provider={decision.provider!r})"
                )

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

        # Lot 21 (Codex review pass 1, HIGH-003): the one point in this graph
        # where the retrieved chunks and the generator's returned citations
        # exist together, so provenance can be checked rather than assumed.
        # Recorded, never enforced — this adds no new failure mode to the
        # graph; it only lets conformance_report() tell the truth.
        self._record_execution_evidence(
            state["context"], state["chunks"], list(answer.citations)
        )

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
        # ExecutionContext.tenant_id is the sole authoritative identity
        # source (contract docstring) — always overwrite whatever tenant_id
        # `request.query` already carries, unconditionally, matching
        # NativeEngineAdapter's identical rule (it never even looks at
        # request.query.tenant_id). Lot 1 (tenant fail-closed): the previous
        # "only fill in if query.tenant_id was empty" condition let a
        # pre-set query.tenant_id outrank the authenticated context — a
        # spoofing vector for any future caller that constructs an
        # EngineRequest with its own Query.tenant_id.
        # Lot 21 (Codex review pass 2, HIGH-005): invalidate any evidence this
        # request id already carries before the attempt starts. `_initial_state()`
        # is the single entry point run()/arun()/astream() all funnel through, so
        # this covers every execution path. Same rationale as
        # `RAGEngine._run()`: a denied or failed retry must not inherit the
        # previous attempt's verified provenance.
        self._execution_evidence.pop(context.request_id, None)
        query = request.query.model_copy(update={"tenant_id": context.tenant_id})
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
