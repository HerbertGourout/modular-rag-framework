"""Semantic conformance tests for the DocumentEngine port (contracts/engine.py).

Lot 7 (docs/refactoring-plan.md) requires "a fake engine and semantic
conformance suite, not merely runtime Protocol checks" — every test below
(besides the first) asserts actual behavior, not just isinstance().
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

import pytest

from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter
from modular_rag.app.container import Container
from modular_rag.contracts.assurance import (
    AssuranceLevel,
    ConformanceReport,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    evidence_status_rank,
)
from modular_rag.contracts.egress import EgressDecision
from modular_rag.contracts.engine import (
    CancellationToken,
    DocumentEngine,
    EngineCapability,
    EngineRequest,
    ExecutionContext,
    GovernanceDecision,
)
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.contracts.security import GuardResult
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import (
    EgressDeniedError,
    EngineCancelledError,
    EngineCapabilityError,
    SecurityError,
)
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.generation.citations.builder import build_citations
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter
from tests.contract.fakes.document_engine import FakeDocumentEngine


def _context(**overrides: object) -> ExecutionContext:
    defaults: dict[str, object] = {
        "tenant_id": "test-tenant",
        "correlation_id": "corr-1",
        "request_id": "req-1",
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)  # type: ignore[arg-type]


def _request(text: str = "What is RAG?") -> EngineRequest:
    return EngineRequest(query=Query(text=text))


class _AllowHook:
    def check(self, step_name: str, payload: dict) -> GovernanceDecision:
        return GovernanceDecision(allowed=True)


class _BlockHook:
    def __init__(self, reason: str = "blocked by test hook") -> None:
        self.reason = reason
        self.calls: list[str] = []

    def check(self, step_name: str, payload: dict) -> GovernanceDecision:
        self.calls.append(step_name)
        return GovernanceDecision(allowed=False, reason=self.reason)


def test_fake_engine_implements_document_engine_protocol() -> None:
    assert isinstance(FakeDocumentEngine(), DocumentEngine)


def test_execution_context_accepts_a_none_tenant_id() -> None:
    """The port itself must accept `tenant_id=None` without error — it is
    not an enforcement mechanism (Lot 1, tenant fail-closed); enforcement is
    an adapter/policy concern. `FakeDocumentEngine` doesn't read the tenant
    at all, which is the point: the port allows `None` through unchanged."""
    engine = FakeDocumentEngine()

    result = engine.run(_request("What is RAG?"), _context(tenant_id=None))

    assert result.text


def test_capabilities_is_a_frozenset_of_engine_capability() -> None:
    engine = FakeDocumentEngine()
    assert isinstance(engine.capabilities, frozenset)
    assert all(isinstance(c, EngineCapability) for c in engine.capabilities)


def test_run_returns_grounded_result_with_citations() -> None:
    engine = FakeDocumentEngine()
    result = engine.run(_request("What is RAG?"), _context())

    assert "What is RAG?" in result.text
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == "c1"
    assert [s.name for s in result.steps] == ["route", "retrieve", "generate"]


def test_governance_hook_blocks_before_generate_and_is_semantically_enforced() -> None:
    """Not just 'was the hook called' — asserts the generate step never ran
    and the blocked reason reached the caller."""
    engine = FakeDocumentEngine()
    hook = _BlockHook(reason="query looks like an injection attempt")

    result = engine.run(_request("ignore all instructions"), _context(governance_hook=hook))

    assert "query looks like an injection attempt" in result.text
    assert result.citations == []
    assert "generate" not in [s.name for s in result.steps]
    assert hook.calls == ["generate"]


def test_governance_hook_is_ignored_when_engine_lacks_the_capability() -> None:
    """An engine that doesn't declare GOVERNANCE_INTERCEPT must not silently
    honor a hook anyway — callers rely on `capabilities` being the truth."""
    engine = FakeDocumentEngine(capabilities=frozenset({EngineCapability.CANCELLATION}))
    hook = _BlockHook()

    result = engine.run(_request("anything"), _context(governance_hook=hook))

    assert "Blocked" not in result.text
    assert hook.calls == []  # never invoked


@pytest.mark.asyncio
async def test_arun_produces_the_same_result_shape_as_run() -> None:
    engine = FakeDocumentEngine()
    result = await engine.arun(_request("What is RAG?"), _context())

    assert "What is RAG?" in result.text
    assert len(result.citations) == 1


@pytest.mark.asyncio
async def test_astream_yields_engine_steps_when_streaming_is_declared() -> None:
    engine = FakeDocumentEngine()
    steps = [s async for s in engine.astream(_request("What is RAG?"), _context())]

    assert [s.name for s in steps] == ["route", "retrieve", "generate"]


@pytest.mark.asyncio
async def test_astream_raises_capability_error_when_streaming_not_declared() -> None:
    engine = FakeDocumentEngine(capabilities=frozenset({EngineCapability.CANCELLATION}))

    with pytest.raises(EngineCapabilityError, match="STREAMING"):
        async for _ in engine.astream(_request("x"), _context()):
            pass


def test_run_raises_engine_cancelled_error_when_token_is_pre_cancelled() -> None:
    engine = FakeDocumentEngine()
    token = CancellationToken()
    token.cancel()

    with pytest.raises(EngineCancelledError):
        engine.run(_request("x"), _context(cancellation_token=token))


def test_cancellation_is_ignored_when_engine_lacks_the_capability() -> None:
    engine = FakeDocumentEngine(capabilities=frozenset({EngineCapability.GOVERNANCE_INTERCEPT}))
    token = CancellationToken()
    token.cancel()

    # Must not raise — the engine doesn't declare CANCELLATION, so a pre-cancelled
    # token is the caller's mistake to check via `capabilities`, not a runtime error.
    result = engine.run(_request("x"), _context(cancellation_token=token))
    assert result.text


def test_name_and_engine_version_are_non_empty_strings() -> None:
    engine = FakeDocumentEngine()
    assert isinstance(engine.name(), str) and engine.name()
    assert isinstance(engine.engine_version(), str) and engine.engine_version()


# ---------------------------------------------------------------------------
# conformance_report() — Lot 21, ADR-0017 (Accepted 2026-09-10)
#
# Rewritten after Codex review pass 1, HIGH-004: the previous version checked
# report shape, determinism, an *assumed* provenance status, and a single
# policy denial. It could therefore stay green while an adapter overclaimed
# most evidence kinds, and its overclaim test asserted the claim was false
# rather than feeding the liar into a reusable assertion that rejects it.
#
# Rewritten again after Codex review pass 2, HIGH-004: probes were still
# *status-agnostic*. Each kind had one boolean check, so an adapter claiming
# AUDIT_COMPLETION=ENFORCED passed on evidence that only showed an audit event
# had been written — which is OBSERVED-strength, not ENFORCED-strength. The
# status ladder was therefore unvalidated: any status above UNSUPPORTED bought
# the same, weakest proof.
#
# What follows is one shared harness, `assert_claims_match_behaviour()`, run
# against every DocumentEngine this repository ships. Its rule:
#
#   for every evidence kind a report claims above UNSUPPORTED, the suite must
#   own a behavioural probe *for that kind at that strength*, and that probe —
#   plus every weaker one defined for the kind — must pass.
#
# A claim with no probe, or with no probe at the claimed strength, is itself a
# conformance failure, so an adapter can neither add a claim nothing checks nor
# promote an existing claim up the ladder without earning it. Honestly
# UNSUPPORTED kinds are skipped — reporting a capability you do not have is the
# correct behaviour, not something to punish.
# ---------------------------------------------------------------------------


class _ProbeResult(NamedTuple):
    passed: bool
    detail: str


# What each rung of the ladder obliges an adapter to demonstrate. These are the
# harness's operational reading of the `EvidenceStatus` docstrings, and the
# failure messages quote them so a future adapter author sees the bar rather
# than just "probe failed".
_STATUS_CONTRACT: dict[EvidenceStatus, str] = {
    EvidenceStatus.OBSERVED: (
        "the stage genuinely ran for this request and left a record of doing so"
    ),
    EvidenceStatus.VERIFIED: (
        "the framework independently compared the claim against what actually happened, "
        "and rejects fabricated evidence rather than trusting a component's own word"
    ),
    EvidenceStatus.ENFORCED: (
        "a denied or failing control actually stops the request — the decision propagates "
        "to the caller instead of being a best-effort side record"
    ),
}

_LADDER: tuple[EvidenceStatus, ...] = (
    EvidenceStatus.OBSERVED,
    EvidenceStatus.VERIFIED,
    EvidenceStatus.ENFORCED,
)


@dataclass(frozen=True)
class _StatusProbe:
    """The behavioural checks a suite owns for one evidence kind, keyed by the
    *strength* a report may claim for it (Codex review pass 2, HIGH-004).

    A claim is honoured only if the check for its own rung exists and passes,
    and every weaker check this probe defines passes too — `EvidenceStatus` is
    a ladder, so ENFORCED is a promise that subsumes OBSERVED, not an
    alternative to it.
    """

    observed: Callable[[], _ProbeResult] | None = None
    verified: Callable[[], _ProbeResult] | None = None
    enforced: Callable[[], _ProbeResult] | None = None

    def check_for(self, status: EvidenceStatus) -> Callable[[], _ProbeResult] | None:
        return {
            EvidenceStatus.OBSERVED: self.observed,
            EvidenceStatus.VERIFIED: self.verified,
            EvidenceStatus.ENFORCED: self.enforced,
        }.get(status)

    def checks_up_to(
        self, claimed: EvidenceStatus
    ) -> list[tuple[EvidenceStatus, Callable[[], _ProbeResult]]]:
        ceiling = evidence_status_rank(claimed)
        checks = []
        for status in _LADDER:
            check = self.check_for(status)
            if check is not None and evidence_status_rank(status) <= ceiling:
                checks.append((status, check))
        return checks


@dataclass
class _EngineFixture:
    """One engine, already exercised, plus a status-aware behavioural probe per
    evidence kind it is allowed to claim."""

    name: str
    engine: DocumentEngine
    context: ExecutionContext
    probes: dict[EvidenceKind, _StatusProbe]


def assert_claims_match_behaviour(fixture: _EngineFixture) -> None:
    """The reusable conformance assertion (Lot 21 required scope item 10).

    Fails for a declared-but-not-honoured capability, for a claim the suite
    cannot behaviourally verify at all, and for a claim pitched at a strength
    the suite cannot verify. Used by the real-adapter tests below *and*, via
    `collect_claim_failures()`, by the negative tests that feed deliberately
    overclaiming engines through this same path.
    """
    failures = collect_claim_failures(fixture)
    assert not failures, "conformance claims not backed by behaviour:\n" + "\n".join(failures)


def collect_claim_failures(fixture: _EngineFixture) -> list[str]:
    report = fixture.engine.conformance_report(fixture.context)
    failures: list[str] = []
    for entry in report.evidence:
        if entry.status is EvidenceStatus.UNSUPPORTED:
            continue  # honestly unsupported — nothing to verify
        claim = f"{fixture.name}: claims {entry.kind.value}={entry.status.value}"
        probe = fixture.probes.get(entry.kind)
        if probe is None:
            failures.append(
                f"{claim} but this suite has no behavioural probe for that kind"
            )
            continue
        if probe.check_for(entry.status) is None:
            failures.append(
                f"{claim} but this suite has no behavioural probe for that kind at "
                f"{entry.status.value} strength, which requires proving that "
                f"{_STATUS_CONTRACT[entry.status]}"
            )
            continue
        for status, check in probe.checks_up_to(entry.status):
            result = check()
            if not result.passed:
                failures.append(
                    f"{claim} but {result.detail} — {status.value} requires that "
                    f"{_STATUS_CONTRACT[status]}"
                )
    return failures


# --- shared component fixtures ----------------------------------------------


class _Hit:
    """Builds a RetrievedChunk carrying the tenant the test contexts use, so
    TenantIsolationPolicy-style filtering does not silently empty the context."""

    @staticmethod
    def make(content: str = "chunk text", tenant_id: str | None = "test-tenant") -> RetrievedChunk:
        return RetrievedChunk(
            chunk=Chunk(doc_id="d", content=content, tenant_id=tenant_id),
            score=0.9,
            rank=1,
            retrieval_method=RetrievalMethod.HYBRID,
        )


class _HitRetriever:
    def __init__(self, hits: list[RetrievedChunk] | None = None) -> None:
        self._hits = hits if hits is not None else [_Hit.make()]

    def retrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return self._hits

    async def aretrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return self._hits

    def name(self) -> str:
        return "hit-retriever"


class _CitingGenerator:
    def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return Answer(
            query_id=query.id, text="grounded answer", citations=build_citations(context)
        )

    async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "citing-generator"


class _AllowingGuard:
    def check_query(self, query):  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def check_answer(self, answer):  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def name(self) -> str:
        return "allowing-guard"


class _DenyingGuard:
    def check_query(self, query):  # type: ignore[no-untyped-def]
        return GuardResult(allowed=False, reason="denied by conformance probe")

    def check_answer(self, answer):  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def name(self) -> str:
        return "denying-guard"


class _AllowingEgressPolicy:
    def check(self, *, classification, provider, operation):  # type: ignore[no-untyped-def]
        return EgressDecision(
            allowed=True,
            reason="allowed",
            classification=classification,
            provider=provider,
            operation=operation,
        )

    def name(self) -> str:
        return "allowing-egress"


class _DenyingEgressPolicy:
    def check(self, *, classification, provider, operation):  # type: ignore[no-untyped-def]
        return EgressDecision(
            allowed=False,
            reason="denied by conformance probe",
            classification=classification,
            provider=provider,
            operation=operation,
        )

    def name(self) -> str:
        return "denying-egress"


class _RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list = []

    def record(self, event) -> None:  # type: ignore[no-untyped-def]
        self.events.append(event)

    async def arecord(self, event) -> None:  # type: ignore[no-untyped-def]
        self.record(event)

    def name(self) -> str:
        return "recording-audit-sink"


class _RecordingReviewQueue:
    def __init__(self, should: bool = True) -> None:
        self._should = should
        self.enqueued: list = []

    def should_review(self, answer) -> bool:  # type: ignore[no-untyped-def]
        return self._should

    def enqueue(self, item) -> None:  # type: ignore[no-untyped-def]
        self.enqueued.append(item)

    def resolve(self, item_id, resolution):  # type: ignore[no-untyped-def]
        return None

    def name(self) -> str:
        return "recording-review-queue"


class _FailingAuditSink:
    """A wired, Protocol-satisfying audit sink whose write always fails.

    The ENFORCED probe for `AUDIT_COMPLETION` (Codex review pass 2, HIGH-004):
    "an audit event was written" only proves OBSERVED. ENFORCED additionally
    promises the record is a precondition of the response, so this sink must
    make the request fail rather than degrade silently.
    """

    def record(self, event) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("audit sink unavailable")

    async def arecord(self, event) -> None:  # type: ignore[no-untyped-def]
        self.record(event)

    def name(self) -> str:
        return "failing-audit-sink"


class _FailingReviewQueue:
    """Routes nothing: `should_review()` says yes, `enqueue()` then fails.

    The ENFORCED probe for `FEEDBACK_REVIEW_ROUTING` — an answer flagged for
    human review that quietly never reaches the queue is precisely the failure
    mode that claim exists to rule out.
    """

    def should_review(self, answer) -> bool:  # type: ignore[no-untyped-def]
        return True

    def enqueue(self, item) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("review queue unavailable")

    def resolve(self, item_id, resolution):  # type: ignore[no-untyped-def]
        return None

    def name(self) -> str:
        return "failing-review-queue"


class _FabricatingGenerator:
    """Cites a genuinely retrieved chunk id while fabricating the passage.

    The VERIFIED probe for `RETRIEVAL_PROVENANCE` (Codex review pass 2,
    HIGH-003/HIGH-004): `contracts.generation.Generator` promises nothing about
    citations, so "the run produced citations" is OBSERVED-strength only.
    VERIFIED means the framework compared them against the retrieved chunks
    itself — which is only demonstrated by an engine *refusing* to report
    VERIFIED for this generator's output.
    """

    def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
        first = context[0]
        return Answer(
            query_id=query.id,
            text="ungrounded answer",
            citations=[
                Citation(
                    chunk_id=first.chunk.id,
                    source="fabricated.pdf",
                    passage="text that was never retrieved",
                    score=first.score,
                )
            ],
        )

    async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "fabricating-generator"


class _AllowingTenantPolicy:
    """Enforces exactly what the real policy's contract promises for these
    probes: deny when no tenant identity is present, otherwise pass through."""

    def enforce_query(self, query) -> None:  # type: ignore[no-untyped-def]
        if not query.tenant_id:
            raise SecurityError("no tenant identity")

    def enforce_ingest(self, tenant_id) -> None:  # type: ignore[no-untyped-def]
        if not tenant_id:
            raise SecurityError("no tenant identity")

    def filter_chunks(self, tenant_id, chunks):  # type: ignore[no-untyped-def]
        return [c for c in chunks if c.chunk.tenant_id in (None, tenant_id)]

    def name(self) -> str:
        return "allowing-tenant-policy"


def _governed_container(**roles: object) -> Container:
    manifest = PipelineManifest(
        id="engine-conformance-test",
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
    return container


def _governed_roles() -> dict[str, object]:
    return {
        "tenant_policy": _AllowingTenantPolicy(),
        "guard": _AllowingGuard(),
        "egress_policy": _AllowingEgressPolicy(),
    }


def _make_native(**roles: object) -> DocumentEngine:
    return NativeEngineAdapter(RAGEngine(_governed_container(**roles)))


def _make_langgraph(**roles: object) -> DocumentEngine:
    return LangGraphEngineAdapter(_governed_container(**roles))


def _raises(engine: DocumentEngine, context: ExecutionContext, expected: type[Exception]) -> bool:
    try:
        engine.run(_request("probe"), context)
    except expected:
        return True
    except Exception:  # noqa: BLE001 - any other error means the probe is inconclusive
        return False
    return False


def _fails(engine: DocumentEngine, context: ExecutionContext) -> bool:
    """True when the request does not complete at all.

    Used where the ENFORCED promise is "this control failing fails the
    request" and the propagated error is the dependency's own (a down audit
    sink or review queue raises whatever its backend raises), not one of the
    framework's typed governance errors.
    """
    try:
        engine.run(_request("probe"), context)
    except Exception:  # noqa: BLE001 - any failure to complete satisfies the claim
        return True
    return False


def _reported_provenance(
    engine: DocumentEngine, context: ExecutionContext
) -> EvidenceStatus:
    return engine.conformance_report(context).evidence_for(
        EvidenceKind.RETRIEVAL_PROVENANCE
    ).status


# --- per-adapter probe wiring ------------------------------------------------


def _native_fixture() -> _EngineFixture:
    audit_sink = _RecordingAuditSink()
    review_queue = _RecordingReviewQueue()
    roles = {**_governed_roles(), "audit_sink": audit_sink, "review_queue": review_queue}
    engine = _make_native(**roles)
    context = _context()
    result = engine.run(_request(), context)

    def provenance_observed() -> _ProbeResult:
        return _ProbeResult(
            bool(result.citations), "the completed run returned no citations at all"
        )

    def provenance_verified() -> _ProbeResult:
        liar = _make_native(**{**roles, "generator": _FabricatingGenerator()})
        fabricated_context = _context(request_id="probe-fabricated-provenance")
        liar.run(_request("probe"), fabricated_context)
        status = _reported_provenance(liar, fabricated_context)
        return _ProbeResult(
            evidence_status_rank(status) < evidence_status_rank(EvidenceStatus.VERIFIED),
            "a generator citing a real chunk id with a fabricated passage was still "
            f"reported as {status.value}",
        )

    def identity_enforced() -> _ProbeResult:
        denied = _raises(
            _make_native(**roles),
            ExecutionContext(tenant_id=None, correlation_id="c", request_id="probe-tenant"),
            SecurityError,
        )
        return _ProbeResult(denied, "a request with no tenant identity was not denied")

    def policy_enforced() -> _ProbeResult:
        denied = _raises(
            _make_native(**{**roles, "guard": _DenyingGuard()}), _context(), SecurityError
        )
        return _ProbeResult(denied, "a denying guard did not block the request")

    def egress_enforced() -> _ProbeResult:
        denied = _raises(
            _make_native(**{**roles, "egress_policy": _DenyingEgressPolicy()}),
            _context(),
            EgressDeniedError,
        )
        return _ProbeResult(denied, "a denying egress policy did not block the request")

    def audit_observed() -> _ProbeResult:
        return _ProbeResult(
            bool(audit_sink.events), "the completed run wrote no audit event at all"
        )

    def audit_enforced() -> _ProbeResult:
        failed = _fails(
            _make_native(**{**roles, "audit_sink": _FailingAuditSink()}),
            _context(request_id="probe-audit-down"),
        )
        return _ProbeResult(
            failed, "the request completed normally while the audit sink was failing"
        )

    def review_observed() -> _ProbeResult:
        return _ProbeResult(
            bool(review_queue.enqueued),
            "should_review() said yes but nothing was routed to the review queue",
        )

    def review_enforced() -> _ProbeResult:
        failed = _fails(
            _make_native(**{**roles, "review_queue": _FailingReviewQueue()}),
            _context(request_id="probe-review-down"),
        )
        return _ProbeResult(
            failed,
            "an answer flagged for human review was returned even though enqueueing it failed",
        )

    return _EngineFixture(
        name="native",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.RETRIEVAL_PROVENANCE: _StatusProbe(
                observed=provenance_observed, verified=provenance_verified
            ),
            EvidenceKind.IDENTITY_TENANT: _StatusProbe(enforced=identity_enforced),
            EvidenceKind.POLICY_DECISION: _StatusProbe(enforced=policy_enforced),
            EvidenceKind.EGRESS_DECISION: _StatusProbe(enforced=egress_enforced),
            EvidenceKind.AUDIT_COMPLETION: _StatusProbe(
                observed=audit_observed, enforced=audit_enforced
            ),
            EvidenceKind.FEEDBACK_REVIEW_ROUTING: _StatusProbe(
                observed=review_observed, enforced=review_enforced
            ),
        },
    )


def _langgraph_fixture() -> _EngineFixture:
    roles = _governed_roles()
    engine = _make_langgraph(**roles)
    context = _context()
    result = engine.run(_request(), context)

    def provenance_observed() -> _ProbeResult:
        return _ProbeResult(
            bool(result.citations), "the completed run returned no citations at all"
        )

    def provenance_verified() -> _ProbeResult:
        liar = _make_langgraph(**{**roles, "generator": _FabricatingGenerator()})
        fabricated_context = _context(request_id="probe-fabricated-provenance")
        liar.run(_request("probe"), fabricated_context)
        status = _reported_provenance(liar, fabricated_context)
        return _ProbeResult(
            evidence_status_rank(status) < evidence_status_rank(EvidenceStatus.VERIFIED),
            "a generator citing a real chunk id with a fabricated passage was still "
            f"reported as {status.value}",
        )

    def identity_enforced() -> _ProbeResult:
        denied = _raises(
            _make_langgraph(**roles),
            ExecutionContext(tenant_id=None, correlation_id="c", request_id="probe-tenant"),
            SecurityError,
        )
        return _ProbeResult(denied, "a request with no tenant identity was not denied")

    def policy_enforced() -> _ProbeResult:
        denied = _raises(
            _make_langgraph(**{**roles, "guard": _DenyingGuard()}), _context(), SecurityError
        )
        return _ProbeResult(denied, "a denying guard did not block the request")

    def egress_enforced() -> _ProbeResult:
        denied = _raises(
            _make_langgraph(**{**roles, "egress_policy": _DenyingEgressPolicy()}),
            _context(),
            EgressDeniedError,
        )
        return _ProbeResult(denied, "a denying egress policy did not block the request")

    def streaming_enforced() -> _ProbeResult:
        """Nothing generated may reach the stream before the pre-output check
        runs: with a denying guard, astream() must fail or yield no
        "generate" step."""
        gated = _make_langgraph(**{**roles, "guard": _DenyingGuard()})

        async def _collect() -> list[str]:
            names: list[str] = []
            async for step in gated.astream(_request("probe"), _context()):
                names.append(step.name)
            return names

        try:
            names = asyncio.run(_collect())
        except SecurityError:
            return _ProbeResult(True, "")
        return _ProbeResult(
            "generate" not in names, "generated output streamed despite a denying guard"
        )

    return _EngineFixture(
        name="langgraph",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.RETRIEVAL_PROVENANCE: _StatusProbe(
                observed=provenance_observed, verified=provenance_verified
            ),
            EvidenceKind.IDENTITY_TENANT: _StatusProbe(enforced=identity_enforced),
            EvidenceKind.POLICY_DECISION: _StatusProbe(enforced=policy_enforced),
            EvidenceKind.EGRESS_DECISION: _StatusProbe(enforced=egress_enforced),
            EvidenceKind.STREAMING_PREVALIDATION: _StatusProbe(enforced=streaming_enforced),
        },
    )


class _FabricatingFakeDocumentEngine(FakeDocumentEngine):
    """Cites genuinely retrieved chunk ids with passages that were never
    retrieved — the fake's equivalent of `_FabricatingGenerator`, overriding
    only the citation-producing seam so the engine's own grounding check still
    runs unmodified underneath it."""

    def build_citations(self, retrieved: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                chunk_id=hit.chunk.id,
                source="fabricated.pdf",
                passage="text that was never retrieved",
                score=hit.score,
            )
            for hit in retrieved
        ]


def _fake_fixture() -> _EngineFixture:
    engine = FakeDocumentEngine()
    hook = _AllowHook()
    context = _context(governance_hook=hook)
    result = engine.run(_request(), context)

    def provenance_observed() -> _ProbeResult:
        return _ProbeResult(
            bool(result.citations), "the completed run returned no citations at all"
        )

    def provenance_verified() -> _ProbeResult:
        liar = _FabricatingFakeDocumentEngine()
        fabricated_context = _context(
            governance_hook=hook, request_id="probe-fabricated-provenance"
        )
        liar.run(_request("probe"), fabricated_context)
        status = _reported_provenance(liar, fabricated_context)
        return _ProbeResult(
            evidence_status_rank(status) < evidence_status_rank(EvidenceStatus.VERIFIED),
            "a citation on a real chunk id with a fabricated passage was still "
            f"reported as {status.value}",
        )

    def policy_enforced() -> _ProbeResult:
        blocking = FakeDocumentEngine()
        blocked = blocking.run(
            _request("probe"), _context(governance_hook=_BlockHook(reason="probe"))
        )
        return _ProbeResult(
            "Blocked" in blocked.text and not blocked.citations,
            "a denying governance hook did not block the request",
        )

    def streaming_enforced() -> _ProbeResult:
        blocking = FakeDocumentEngine()

        async def _collect() -> list[str]:
            return [
                step.name
                async for step in blocking.astream(
                    _request("probe"), _context(governance_hook=_BlockHook(reason="probe"))
                )
            ]

        names = asyncio.run(_collect())
        return _ProbeResult(
            "generate" not in names, "generated output streamed despite a denying hook"
        )

    return _EngineFixture(
        name="fake",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.RETRIEVAL_PROVENANCE: _StatusProbe(
                observed=provenance_observed, verified=provenance_verified
            ),
            EvidenceKind.POLICY_DECISION: _StatusProbe(enforced=policy_enforced),
            EvidenceKind.STREAMING_PREVALIDATION: _StatusProbe(enforced=streaming_enforced),
        },
    )


_FIXTURE_FACTORIES: dict[str, Callable[[], _EngineFixture]] = {
    "fake": _fake_fixture,
    "native": _native_fixture,
    "langgraph": _langgraph_fixture,
}


# --- the shared suite, run against every shipped engine ----------------------


@pytest.mark.parametrize("engine_name", sorted(_FIXTURE_FACTORIES))
def test_every_claimed_evidence_kind_is_backed_by_real_behaviour(engine_name: str) -> None:
    """Lot 21's core acceptance criterion, and the direct answer to Codex
    review pass 1's HIGH-004: the same semantic suite validates each
    non-unsupported claim made by the fake *and* both real shipped adapters."""
    assert_claims_match_behaviour(_FIXTURE_FACTORIES[engine_name]())


@pytest.mark.parametrize("engine_name", sorted(_FIXTURE_FACTORIES))
def test_conformance_report_is_a_valid_report_for_every_shipped_engine(engine_name: str) -> None:
    fixture = _FIXTURE_FACTORIES[engine_name]()

    report = fixture.engine.conformance_report(fixture.context)

    assert isinstance(report, ConformanceReport)
    assert report.adapter_name
    assert report.adapter_version
    assert {entry.kind for entry in report.evidence} == set(EvidenceKind)
    assert report.achieved_level in set(AssuranceLevel)


@pytest.mark.parametrize("engine_name", sorted(_FIXTURE_FACTORIES))
def test_conformance_report_is_deterministic_for_the_same_wiring_and_context(
    engine_name: str,
) -> None:
    fixture = _FIXTURE_FACTORIES[engine_name]()

    first = fixture.engine.conformance_report(fixture.context)
    second = fixture.engine.conformance_report(fixture.context)

    assert first == second


@pytest.mark.parametrize("engine_name", sorted(_FIXTURE_FACTORIES))
def test_no_engine_claims_provenance_for_a_request_it_never_served(engine_name: str) -> None:
    """Codex review pass 1, HIGH-003: provenance is execution-derived, so a
    context that never ran must not inherit another request's evidence."""
    fixture = _FIXTURE_FACTORIES[engine_name]()

    unrelated = fixture.engine.conformance_report(_context(request_id="never-executed"))

    assert (
        unrelated.evidence_for(EvidenceKind.RETRIEVAL_PROVENANCE).status
        == EvidenceStatus.UNSUPPORTED
    )


def test_the_suite_has_a_real_honestly_unsupported_capability_to_exercise() -> None:
    """Sanity check on the fixtures themselves: at least one shipped engine
    declares no STREAMING at all, so "honestly unsupported is not a failure"
    is exercised rather than assumed."""
    assert EngineCapability.STREAMING not in _make_native().capabilities
    assert EngineCapability.STREAMING in _make_langgraph().capabilities


# --- the negative input: a deliberately overclaiming engine ------------------


class _OverclaimingFakeDocumentEngine(FakeDocumentEngine):
    """Claims `IDENTITY_TENANT: ENFORCED` while doing nothing of the sort —
    this fake never reads `context.tenant_id` at all. Fed through the *same*
    `collect_claim_failures()` path the real adapters use, so the negative
    test proves the harness rejects a false claim rather than asserting the
    claim is false by hand (Codex review pass 1, HIGH-004)."""

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        honest = super().conformance_report(context)
        dishonest = tuple(
            EvidenceEntry(entry.kind, EvidenceStatus.ENFORCED, entry.detail)
            if entry.kind is EvidenceKind.IDENTITY_TENANT
            else entry
            for entry in honest.evidence
        )
        return ConformanceReport(
            adapter_name="overclaiming-fake", adapter_version="0.0.0", evidence=dishonest
        )


def test_the_shared_harness_rejects_a_deliberately_overclaiming_engine() -> None:
    engine = _OverclaimingFakeDocumentEngine()
    context = _context(governance_hook=_AllowHook())
    engine.run(_request(), context)

    def tenant_probe() -> _ProbeResult:
        """This fake ignores tenant identity entirely, so a request with none
        completes normally — the claim of ENFORCED is false."""
        result = engine.run(
            _request("probe"),
            ExecutionContext(tenant_id=None, correlation_id="c", request_id="probe-tenant"),
        )
        return _ProbeResult(
            not result.text, "a request with no tenant identity was not denied"
        )

    passing = _StatusProbe(
        observed=lambda: _ProbeResult(True, ""),
        verified=lambda: _ProbeResult(True, ""),
        enforced=lambda: _ProbeResult(True, ""),
    )
    fixture = _EngineFixture(
        name="overclaiming-fake",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.IDENTITY_TENANT: _StatusProbe(enforced=tenant_probe),
            EvidenceKind.RETRIEVAL_PROVENANCE: passing,
            EvidenceKind.POLICY_DECISION: passing,
            EvidenceKind.STREAMING_PREVALIDATION: passing,
        },
    )

    failures = collect_claim_failures(fixture)

    assert any("identity_tenant" in failure for failure in failures), failures
    with pytest.raises(AssertionError, match="identity_tenant"):
        assert_claims_match_behaviour(fixture)


def test_the_shared_harness_rejects_a_claim_it_cannot_verify_at_all() -> None:
    """A claim with no behavioural probe is a conformance failure in itself,
    so an adapter cannot add a new claim that nothing in this suite checks."""
    engine = FakeDocumentEngine()
    context = _context(governance_hook=_AllowHook())
    engine.run(_request(), context)

    fixture = _EngineFixture(name="unprobed", engine=engine, context=context, probes={})

    failures = collect_claim_failures(fixture)

    assert any("no behavioural probe" in failure for failure in failures), failures


def test_the_shared_harness_rejects_a_claim_probed_only_at_a_weaker_strength() -> None:
    """Codex review pass 2, HIGH-004: the whole point of the status ladder is
    that ENFORCED costs more to claim than OBSERVED. A probe that can only
    show the stage ran must not be able to certify that the stage blocks."""
    engine = FakeDocumentEngine()
    context = _context(governance_hook=_AllowHook())
    engine.run(_request(), context)

    # `policy_decision` is claimed ENFORCED by this engine; offer only an
    # OBSERVED-strength check for it.
    fixture = _EngineFixture(
        name="weakly-probed",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.RETRIEVAL_PROVENANCE: _StatusProbe(
                observed=lambda: _ProbeResult(True, ""),
                verified=lambda: _ProbeResult(True, ""),
            ),
            EvidenceKind.POLICY_DECISION: _StatusProbe(
                observed=lambda: _ProbeResult(True, "")
            ),
            EvidenceKind.STREAMING_PREVALIDATION: _StatusProbe(
                enforced=lambda: _ProbeResult(True, "")
            ),
        },
    )

    failures = collect_claim_failures(fixture)

    assert any(
        "policy_decision" in failure and "at enforced strength" in failure
        for failure in failures
    ), failures


def test_a_weaker_check_still_runs_for_a_stronger_claim() -> None:
    """ENFORCED subsumes OBSERVED, so a failing OBSERVED check invalidates an
    ENFORCED claim even when the ENFORCED check itself passes."""
    engine = FakeDocumentEngine()
    context = _context(governance_hook=_AllowHook())
    engine.run(_request(), context)

    fixture = _EngineFixture(
        name="ladder",
        engine=engine,
        context=context,
        probes={
            EvidenceKind.RETRIEVAL_PROVENANCE: _StatusProbe(
                observed=lambda: _ProbeResult(True, ""),
                verified=lambda: _ProbeResult(True, ""),
            ),
            EvidenceKind.POLICY_DECISION: _StatusProbe(
                observed=lambda: _ProbeResult(False, "the guard step never ran"),
                enforced=lambda: _ProbeResult(True, ""),
            ),
            EvidenceKind.STREAMING_PREVALIDATION: _StatusProbe(
                enforced=lambda: _ProbeResult(True, "")
            ),
        },
    )

    failures = collect_claim_failures(fixture)

    assert any("the guard step never ran" in failure for failure in failures), failures


# --- a reused request id must never inherit an earlier attempt's evidence ----
# Codex review pass 2, HIGH-005.


class _TogglingGuard:
    """Allows until `deny` is set, so one engine instance can serve a request
    successfully and then fail a retry carrying the same request id."""

    def __init__(self) -> None:
        self.deny = False

    def check_query(self, query):  # type: ignore[no-untyped-def]
        if self.deny:
            return GuardResult(allowed=False, reason="denied on retry")
        return GuardResult(allowed=True)

    def check_answer(self, answer):  # type: ignore[no-untyped-def]
        return GuardResult(allowed=True)

    def name(self) -> str:
        return "toggling-guard"


def _retry_scenario(
    engine_name: str,
) -> tuple[DocumentEngine, Callable[[ExecutionContext], None], Callable[[ExecutionContext], None]]:
    """One engine instance plus (succeed, then_fail) callables that reuse
    whatever context they are handed — including its request id."""
    if engine_name == "fake":
        fake = FakeDocumentEngine()

        def fake_succeed(context: ExecutionContext) -> None:
            fake.run(_request(), context)

        def fake_fail(context: ExecutionContext) -> None:
            blocked = fake.run(
                _request(),
                _context(
                    request_id=context.request_id,
                    governance_hook=_BlockHook(reason="denied on retry"),
                ),
            )
            assert not blocked.citations

        return fake, fake_succeed, fake_fail

    guard = _TogglingGuard()
    roles = {**_governed_roles(), "guard": guard}
    engine = _make_native(**roles) if engine_name == "native" else _make_langgraph(**roles)

    def succeed(context: ExecutionContext) -> None:
        engine.run(_request(), context)

    def fail(context: ExecutionContext) -> None:
        guard.deny = True
        try:
            with pytest.raises(SecurityError):
                engine.run(_request(), context)
        finally:
            guard.deny = False

    return engine, succeed, fail


@pytest.mark.parametrize("engine_name", ["fake", "langgraph", "native"])
def test_a_reused_request_id_never_inherits_an_earlier_attempts_provenance(
    engine_name: str,
) -> None:
    """Codex review pass 2, HIGH-005: execution evidence is keyed by request
    id, so a retry of an already-served id (a client retry, a replayed job)
    would otherwise report the *first* attempt's verified provenance for a
    second attempt that produced no answer at all."""
    engine, succeed, fail = _retry_scenario(engine_name)
    context = _context(request_id="reused-request-id")

    succeed(context)
    assert _reported_provenance(engine, context) == EvidenceStatus.VERIFIED

    fail(context)
    assert _reported_provenance(engine, context) == EvidenceStatus.UNSUPPORTED
