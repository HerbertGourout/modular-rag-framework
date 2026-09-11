"""Tests for orchestration/native_engine.py (NativeEngineAdapter, Lot 8).

Proves the adapter (a) conforms to DocumentEngine, (b) produces results in
parity with calling the wrapped RAGEngine directly, and (c) is honest about
what it can't do — capabilities declared empty, governance hook and
cancellation token both correctly ignored rather than silently mishandled,
per the semantics established in tests/contract/test_engine_conformance.py.
"""
from __future__ import annotations

import pytest

from modular_rag.app.container import Container
from modular_rag.contracts.assurance import AssuranceLevel, EvidenceKind, EvidenceStatus
from modular_rag.contracts.egress import EgressDecision
from modular_rag.contracts.engine import (
    CancellationToken,
    DocumentEngine,
    EngineRequest,
    ExecutionContext,
)
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.contracts.security import GuardResult
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import EngineCapabilityError
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import TraceStep
from modular_rag.generation.citations.builder import build_citations
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter


class _FakeRetriever:
    def retrieve(self, query, k=10):
        return []

    async def aretrieve(self, query, k=10):
        return []

    def name(self) -> str:
        return "fake-retriever"


class _FakeGenerator:
    def __init__(self) -> None:
        self.last_query: Query | None = None

    def generate(self, query, context, trace) -> Answer:
        self.last_query = query
        return Answer(query_id=query.id, text=f"native answer to '{query.text}'")

    async def agenerate(self, query, context, trace) -> Answer:
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "fake-generator"


def _rag_engine() -> RAGEngine:
    return _rag_engine_and_container()[0]


def _rag_engine_and_container() -> tuple[RAGEngine, Container]:
    manifest = PipelineManifest(
        id="native-adapter-test",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", object())
    container.register("indexer", object())
    container.register("retriever", _FakeRetriever())
    container.register("generator", _FakeGenerator())
    return RAGEngine(container), container


def test_native_adapter_implements_document_engine_protocol() -> None:
    assert isinstance(NativeEngineAdapter(_rag_engine()), DocumentEngine)


def test_native_adapter_declares_no_capabilities() -> None:
    """Honest, not a placeholder: RAGEngine has no native streaming,
    cancellation, tool-use, multi-turn, or GovernanceHook-shaped
    interception today — see the module docstring for why."""
    adapter = NativeEngineAdapter(_rag_engine())
    assert adapter.capabilities == frozenset()


def test_run_parity_with_calling_rag_engine_directly() -> None:
    """The actual point of Lot 8: the adapter must not change what the
    native engine does, only how it's addressed."""
    rag_engine = _rag_engine()
    adapter = NativeEngineAdapter(rag_engine)
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")

    direct_answer = rag_engine.answer("What is RAG?")
    adapted_result = adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)

    # Each call generates its own Query/Trace id internally, so trace_ids
    # necessarily differ across two separate invocations — parity is about
    # the *answer text* being identical for an identical question, and both
    # having a trace_id at all, not the ids matching each other.
    assert adapted_result.text == direct_answer.text != ""
    assert adapted_result.metadata.get("trace_id")
    assert direct_answer.trace_id


@pytest.mark.asyncio
async def test_arun_matches_run() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")
    request = EngineRequest(query=Query(text="What is RAG?"))

    sync_result = adapter.run(request, context)
    async_result = await adapter.arun(request, context)

    assert sync_result.text == async_result.text


@pytest.mark.asyncio
async def test_astream_raises_capability_error_since_streaming_is_not_declared() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")

    with pytest.raises(EngineCapabilityError, match="STREAMING"):
        async for _ in adapter.astream(EngineRequest(query=Query(text="x")), context):
            pass


def test_governance_hook_is_ignored_since_the_capability_is_not_declared() -> None:
    class _AlwaysBlockHook:
        def check(self, step_name, payload):
            from modular_rag.contracts.engine import GovernanceDecision

            return GovernanceDecision(allowed=False, reason="should be ignored")

    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(
        tenant_id="t", correlation_id="c", request_id="r", governance_hook=_AlwaysBlockHook()
    )

    result = adapter.run(EngineRequest(query=Query(text="anything")), context)

    assert "should be ignored" not in result.text
    assert "native answer" in result.text


def test_pre_cancelled_token_is_ignored_since_cancellation_is_not_declared() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    token = CancellationToken()
    token.cancel()
    context = ExecutionContext(
        tenant_id="t", correlation_id="c", request_id="r", cancellation_token=token
    )

    result = adapter.run(EngineRequest(query=Query(text="anything")), context)

    assert result.text  # did not raise


def test_run_propagates_execution_context_tenant_id_to_the_underlying_query() -> None:
    """Lot 11b (docs/refactoring-plan.md): "Propagate authenticated identity
    and tenant through ExecutionContext" — `context.tenant_id` must reach
    the `Query` the wrapped `RAGEngine` actually processes, not be dropped
    at the adapter boundary."""
    rag_engine, container = _rag_engine_and_container()
    adapter = NativeEngineAdapter(rag_engine)
    context = ExecutionContext(tenant_id="acme-corp", correlation_id="c", request_id="r")

    adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)

    assert container.generator.last_query.tenant_id == "acme-corp"


def test_run_with_none_context_tenant_id_leaves_the_underlying_query_tenant_id_none() -> None:
    """Lot 1 (tenant fail-closed): a `None` context.tenant_id (no verified
    identity) must reach RAGEngine.answer() as `None`, not a fabricated
    placeholder — this is the adapter-boundary half of the fix; the other
    half (ApplicationService no longer fabricating `"default"`) is covered
    in tests/unit/app/test_application.py."""
    rag_engine, container = _rag_engine_and_container()
    adapter = NativeEngineAdapter(rag_engine)
    context = ExecutionContext(tenant_id=None, correlation_id="c", request_id="r")

    adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)

    assert container.generator.last_query.tenant_id is None


def test_name_and_version_are_non_empty() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    assert adapter.name() == "native"
    assert isinstance(adapter.engine_version(), str) and adapter.engine_version()


# ---------------------------------------------------------------------------
# conformance_report() — Lot 21, ADR-0017 (Accepted 2026-09-10)
#
# Rewritten after Codex review pass 1. Every fixture below uses components
# that actually satisfy their contract Protocol, because HIGH-002 proved that
# plain `object()` stand-ins used to earn ENFORCED for every governed kind and
# then fail the first real request; and every provenance assertion runs a real
# request first, because HIGH-003 proved a status asserted from wiring alone
# was an overclaim.
# ---------------------------------------------------------------------------


class _RealTenantPolicy:
    def enforce_query(self, query) -> None:  # type: ignore[no-untyped-def]
        return None

    def enforce_ingest(self, tenant_id) -> None:  # type: ignore[no-untyped-def]
        return None

    def filter_chunks(self, tenant_id, chunks):  # type: ignore[no-untyped-def]
        return chunks

    def name(self) -> str:
        return "real-tenant-policy"


class _RealGuard:
    def check_query(self, query) -> GuardResult:  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def check_answer(self, answer) -> GuardResult:  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def name(self) -> str:
        return "real-guard"


class _RealEgressPolicy:
    def check(self, *, classification, provider, operation):  # type: ignore[no-untyped-def]
        return EgressDecision(
            allowed=True,
            reason="allowed by test policy",
            classification=classification,
            provider=provider,
            operation=operation,
        )

    def name(self) -> str:
        return "real-egress-policy"


class _RealAuditSink:
    def __init__(self) -> None:
        self.events: list = []

    def record(self, event) -> None:  # type: ignore[no-untyped-def]
        self.events.append(event)

    async def arecord(self, event) -> None:  # type: ignore[no-untyped-def]
        self.record(event)

    def name(self) -> str:
        return "real-audit-sink"


class _RealReviewQueue:
    def should_review(self, answer) -> bool:  # type: ignore[no-untyped-def]
        return False

    def enqueue(self, item) -> None:  # type: ignore[no-untyped-def]
        return None

    def resolve(self, item_id, resolution):  # type: ignore[no-untyped-def]
        return None

    def name(self) -> str:
        return "real-review-queue"


class _CitingGenerator:
    """Returns citations genuinely built from the retrieved chunks — the
    honest case the framework's grounding check should mark VERIFIED."""

    def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return Answer(
            query_id=query.id, text="grounded answer", citations=build_citations(context)
        )

    async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "citing-generator"


def _hit(content: str = "chunk text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(doc_id="d", content=content),
        score=0.9,
        rank=1,
        retrieval_method=RetrievalMethod.HYBRID,
    )


class _HitRetriever:
    def __init__(self, hits: list[RetrievedChunk] | None = None) -> None:
        self._hits = hits if hits is not None else [_hit()]

    def retrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return self._hits

    async def aretrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return self._hits

    def name(self) -> str:
        return "hit-retriever"


def _governed_engine(**roles: object) -> tuple[NativeEngineAdapter, Container]:
    """A container whose generator/retriever really produce grounded
    citations, plus whichever Protocol-satisfying governance roles a test
    asks for."""
    manifest = PipelineManifest(
        id="native-conformance-test",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", object())
    container.register("indexer", object())
    container.register("retriever", _HitRetriever())
    container.register("generator", _CitingGenerator())
    for role, component in roles.items():
        container.register(role, component)
    return NativeEngineAdapter(RAGEngine(container)), container


def _context(request_id: str = "req-1") -> ExecutionContext:
    return ExecutionContext(tenant_id="t", correlation_id="c", request_id=request_id)


def _run_once(adapter: NativeEngineAdapter, context: ExecutionContext) -> None:
    adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)


def test_conformance_report_with_no_governance_wired_achieves_l0() -> None:
    adapter, _ = _governed_engine()

    report = adapter.conformance_report(_context())

    assert report.adapter_name == "native"
    assert report.achieved_level == AssuranceLevel.L0
    assert report.evidence_for(EvidenceKind.IDENTITY_TENANT).status == EvidenceStatus.UNSUPPORTED
    assert (
        report.evidence_for(EvidenceKind.STREAMING_PREVALIDATION).status
        == EvidenceStatus.UNSUPPORTED
    )


def test_conformance_report_claims_no_provenance_before_any_execution() -> None:
    """Codex review pass 1, HIGH-003: provenance is execution-derived. Before
    a request runs there is nothing to have verified, and the report must say
    so rather than assume the generator will behave."""
    adapter, _ = _governed_engine()

    status = adapter.conformance_report(_context()).evidence_for(
        EvidenceKind.RETRIEVAL_PROVENANCE
    ).status

    assert status == EvidenceStatus.UNSUPPORTED


def test_conformance_report_verifies_provenance_after_a_grounded_execution() -> None:
    adapter, _ = _governed_engine()
    context = _context()

    _run_once(adapter, context)

    assert (
        adapter.conformance_report(context).evidence_for(
            EvidenceKind.RETRIEVAL_PROVENANCE
        ).status
        == EvidenceStatus.VERIFIED
    )


def test_conformance_report_does_not_verify_provenance_for_a_zero_citation_generator() -> None:
    """The exact HIGH-003 reproduction, as a regression test: a generator that
    returns no citations must never yield VERIFIED provenance, even though it
    fully satisfies the `Generator` Protocol."""

    class _NoCitationGenerator:
        def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
            return Answer(query_id=query.id, text="ungrounded answer")

        async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
            return self.generate(query, context, trace)

        def name(self) -> str:
            return "no-citation-generator"

    adapter, container = _governed_engine()
    container.register("generator", _NoCitationGenerator())
    context = _context()

    _run_once(adapter, context)

    assert (
        adapter.conformance_report(context).evidence_for(
            EvidenceKind.RETRIEVAL_PROVENANCE
        ).status
        == EvidenceStatus.UNSUPPORTED
    )


def test_conformance_report_observes_but_does_not_verify_ungrounded_citations() -> None:
    """Citations that name chunks this request never retrieved: the framework
    saw provenance data and could not verify it."""

    class _UngroundedGenerator:
        def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
            return Answer(
                query_id=query.id,
                text="answer",
                citations=[
                    Citation(chunk_id="never-retrieved", source="s", passage="p", score=0.1)
                ],
            )

        async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
            return self.generate(query, context, trace)

        def name(self) -> str:
            return "ungrounded-generator"

    adapter, container = _governed_engine()
    container.register("generator", _UngroundedGenerator())
    context = _context()

    _run_once(adapter, context)

    assert (
        adapter.conformance_report(context).evidence_for(
            EvidenceKind.RETRIEVAL_PROVENANCE
        ).status
        == EvidenceStatus.OBSERVED
    )


def test_execution_evidence_is_never_attributed_to_another_request() -> None:
    """Bounded per-request evidence must not leak across requests: a report
    for a context that never executed falls back to the conservative status,
    never to the previous request's verified provenance."""
    adapter, _ = _governed_engine()
    executed = _context("req-executed")

    _run_once(adapter, executed)

    other = adapter.conformance_report(_context("req-never-ran"))
    assert (
        other.evidence_for(EvidenceKind.RETRIEVAL_PROVENANCE).status
        == EvidenceStatus.UNSUPPORTED
    )


def test_conformance_report_rejects_components_that_do_not_satisfy_their_protocol() -> None:
    """The exact HIGH-002 reproduction, as a regression test: plain `object()`
    stand-ins used to earn ENFORCED for every governed kind and report L2,
    then fail the first request with AttributeError."""
    adapter, _ = _governed_engine(
        tenant_policy=object(), guard=object(), egress_policy=object(), audit_sink=object()
    )

    report = adapter.conformance_report(_context())

    assert report.achieved_level == AssuranceLevel.L0
    for kind in (
        EvidenceKind.IDENTITY_TENANT,
        EvidenceKind.EGRESS_DECISION,
        EvidenceKind.POLICY_DECISION,
        EvidenceKind.AUDIT_COMPLETION,
    ):
        assert report.evidence_for(kind).status == EvidenceStatus.UNSUPPORTED, kind


def test_conformance_report_reaches_l2_with_real_controls_after_a_grounded_execution() -> None:
    """The positive case, now requiring both halves: Protocol-satisfying
    governance components *and* a real execution that earned its provenance."""
    adapter, _ = _governed_engine(
        tenant_policy=_RealTenantPolicy(),
        guard=_RealGuard(),
        egress_policy=_RealEgressPolicy(),
        audit_sink=_RealAuditSink(),
        review_queue=_RealReviewQueue(),
    )
    context = _context()

    _run_once(adapter, context)
    report = adapter.conformance_report(context)

    assert report.achieved_level == AssuranceLevel.L2
    for kind in (
        EvidenceKind.IDENTITY_TENANT,
        EvidenceKind.EGRESS_DECISION,
        EvidenceKind.POLICY_DECISION,
        EvidenceKind.AUDIT_COMPLETION,
        EvidenceKind.FEEDBACK_REVIEW_ROUTING,
    ):
        assert report.evidence_for(kind).status == EvidenceStatus.ENFORCED, kind


def test_conformance_report_stays_below_l2_without_an_audit_sink() -> None:
    """ADR-0017 §6 requires audit completion ENFORCED at L2 — Codex review
    pass 1 (HIGH-001) found OBSERVED was being accepted."""
    adapter, _ = _governed_engine(
        tenant_policy=_RealTenantPolicy(),
        guard=_RealGuard(),
        egress_policy=_RealEgressPolicy(),
        review_queue=_RealReviewQueue(),
    )
    context = _context()

    _run_once(adapter, context)

    assert adapter.conformance_report(context).achieved_level == AssuranceLevel.L1


def test_conformance_report_policy_decision_is_enforced_by_policy_engine_alone() -> None:
    """POLICY_DECISION does not require `guard` specifically — RAGEngine also
    enforces via Container.policy_engine.enforce_query(). There is no
    PolicyEngine Protocol, so the method actually called is what gets
    validated, not mere presence."""

    class _RealPolicyEngine:
        def enforce_query(self, query) -> None:  # type: ignore[no-untyped-def]
            return None

    adapter, _ = _governed_engine(policy_engine=_RealPolicyEngine())

    status = adapter.conformance_report(_context()).evidence_for(
        EvidenceKind.POLICY_DECISION
    ).status

    assert status == EvidenceStatus.ENFORCED


def test_conformance_report_policy_decision_rejects_a_policy_engine_without_enforce_query() -> (
    None
):
    adapter, _ = _governed_engine(policy_engine=object())

    status = adapter.conformance_report(_context()).evidence_for(
        EvidenceKind.POLICY_DECISION
    ).status

    assert status == EvidenceStatus.UNSUPPORTED


def test_conformance_report_usage_cost_requires_real_token_evidence_not_just_a_meter() -> None:
    """Codex review pass 1, MEDIUM-001: a wired Meter is necessary but not
    sufficient. `_CitingGenerator` appends no TraceStep, so no token/cost data
    exists for this request even though a Meter is wired."""

    class _RealMeter:
        def counter(self, name, value=1, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def histogram(self, name, value, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def gauge(self, name, value, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def name(self) -> str:
            return "real-meter"

    adapter, _ = _governed_engine(meter=_RealMeter())
    context = _context()

    _run_once(adapter, context)

    assert (
        adapter.conformance_report(context).evidence_for(EvidenceKind.USAGE_COST).status
        == EvidenceStatus.UNSUPPORTED
    )


def test_conformance_report_usage_cost_is_observed_when_the_generator_emits_token_evidence() -> (
    None
):
    class _RealMeter:
        def counter(self, name, value=1, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def histogram(self, name, value, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def gauge(self, name, value, attributes=None):  # type: ignore[no-untyped-def]
            return None

        def name(self) -> str:
            return "real-meter"

    class _TokenReportingGenerator:
        def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
            trace.add_step(
                TraceStep(name="test_generate", input_tokens=11, output_tokens=7, metadata={})
            )
            return Answer(
                query_id=query.id, text="answer", citations=build_citations(context)
            )

        async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
            return self.generate(query, context, trace)

        def name(self) -> str:
            return "token-reporting-generator"

    adapter, container = _governed_engine(meter=_RealMeter())
    container.register("generator", _TokenReportingGenerator())
    context = _context()

    _run_once(adapter, context)

    assert (
        adapter.conformance_report(context).evidence_for(EvidenceKind.USAGE_COST).status
        == EvidenceStatus.OBSERVED
    )


def test_conformance_report_is_deterministic_for_the_same_wiring_and_context() -> None:
    adapter, _ = _governed_engine(tenant_policy=_RealTenantPolicy())
    context = _context()

    assert adapter.conformance_report(context) == adapter.conformance_report(context)
