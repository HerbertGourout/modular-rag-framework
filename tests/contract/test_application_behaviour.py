"""Behavioural probes for the existing-application boundary (Lot 22, ADR-0018 §9-§12).

`test_application_conformance.py` pins the *declarative* contract. This file
is the delivery gate ADR-0018 §9 describes: a profile claims control points,
egress paths and evidence, and each claim above `UNAVAILABLE` must be backed by
a probe that exercises *that attachment* against the application's real
behaviour. A probe that exercised the adapter's own wrapper instead of the
application's bypass path would prove nothing, so every probe asserts an effect
on the application (`provider_calls`, `tool_calls`, `invocations`), not merely a
raised exception.

The harness is run against honest fixtures with different hook surfaces and,
as negative controls, against fixtures that overclaim or hide an egress path:
a gate that never fails has not been shown to gate anything.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import NamedTuple

import pytest

from modular_rag.contracts.application import (
    ApplicationProfile,
    ApplicationProfileProvider,
    ControlPoint,
    ControlPointBinding,
    ControlPointSupport,
    EgressPath,
    evidence_ceiling,
    required_audit_events,
)
from modular_rag.contracts.assurance import (
    AssuranceLevel,
    EvidenceKind,
    EvidenceStatus,
    evidence_status_rank,
)
from modular_rag.contracts.audit import AuditEventType
from modular_rag.contracts.engine import (
    DocumentEngine,
    EngineCapability,
    EngineRequest,
    ExecutionContext,
)
from modular_rag.core.errors import EngineCapabilityError, PolicyViolationError
from modular_rag.core.models.query import Query
from tests.contract.fakes.foreign_application import (
    APP_CLAIMED_TENANT,
    TENANT_A,
    TENANT_B,
    AuditLog,
    Controls,
    ForeignApp,
    ForeignApplicationAdapter,
)

Make = Callable[..., ForeignApplicationAdapter]

_ALL_HOOKS_BLOCKING = {
    ControlPoint.RETRIEVAL_RESULT: True,
    ControlPoint.PRE_MODEL_EGRESS: True,
    ControlPoint.TOOL_INVOCATION: True,
    ControlPoint.STREAM_CHUNK: True,
}


def _context(tenant: str | None = TENANT_A, request_id: str = "req-1") -> ExecutionContext:
    return ExecutionContext(tenant_id=tenant, correlation_id="corr-1", request_id=request_id)


def _request(text: str = "what is the policy?") -> EngineRequest:
    return EngineRequest(query=Query(text=text))


def _factory(
    *, review: bool = False, **app_kwargs: object
) -> Make:
    def make(*, controls: Controls | None = None, audit: AuditLog | None = None):
        return ForeignApplicationAdapter(
            ForeignApp(**app_kwargs),  # type: ignore[arg-type]
            controls=controls,
            audit=audit,
            review_sink=(lambda _request_id: None) if review else None,
        )

    return make


def _governed(**overrides: object) -> Make:
    kwargs: dict[str, object] = {
        "hook_surface": dict(_ALL_HOOKS_BLOCKING),
        "model_paths": {"completion": True, "rerank": True},
        "tools": ("search",),
        "streams": True,
    }
    kwargs.update(overrides)
    return _factory(review=True, **kwargs)


def _partial() -> Make:
    """Hooks exist but cannot block, and one model call bypasses them."""
    return _factory(
        hook_surface={
            ControlPoint.RETRIEVAL_RESULT: False,
            ControlPoint.PRE_MODEL_EGRESS: False,
            ControlPoint.TOOL_INVOCATION: False,
        },
        model_paths={"completion": True, "fallback": False},
        tools=("search",),
    )


def _opaque() -> Make:
    """The realistic floor: the adapter owns the call and nothing else."""
    return _factory(model_paths={"completion": False})


class _Overclaiming(ForeignApplicationAdapter):
    """Declares every hook blocking although the application's hooks are
    observe-only — the exact overclaim the probes exist to reject."""

    @property
    def application_profile(self) -> ApplicationProfile:
        honest = super().application_profile
        bindings = tuple(
            ControlPointBinding(b.point, ControlPointSupport.ENFORCED) for b in honest.bindings
        )
        paths = tuple(
            EgressPath(p.name, p.kind, ControlPoint.PRE_MODEL_EGRESS, ControlPointSupport.ENFORCED)
            for p in honest.egress_paths
        )
        return dataclasses.replace(
            honest,
            bindings=bindings,
            egress_paths=paths,
            expected_audit_events=tuple(
                dataclasses.replace(event, mandatory=True)
                for event in honest.expected_audit_events
            )
            + tuple(
                type(honest.expected_audit_events[0])(event, mandatory=True)
                for event in sorted(
                    required_audit_events(bindings, paths)
                    - {e.event_type for e in honest.expected_audit_events}
                )
            ),
        )


def _overclaiming() -> Make:
    def make(*, controls: Controls | None = None, audit: AuditLog | None = None):
        return _Overclaiming(
            ForeignApp(
                hook_surface={
                    ControlPoint.RETRIEVAL_RESULT: False,
                    ControlPoint.PRE_MODEL_EGRESS: False,
                    ControlPoint.TOOL_INVOCATION: False,
                    ControlPoint.STREAM_CHUNK: False,
                },
                model_paths={"completion": True},
                tools=("search",),
                streams=True,
            ),
            controls=controls,
            audit=audit,
            review_sink=lambda _request_id: None,
        )

    return make


class _Fixture(NamedTuple):
    make: Make
    # None: this fixture withholds the result for a normal request (a
    # tenant-blind application), so there is no served request to report on.
    expected_level: AssuranceLevel | None


HONEST_FIXTURES: dict[str, _Fixture] = {
    "governed": _Fixture(_governed(), AssuranceLevel.L2),
    "governed-over-a-tenant-blind-retriever": _Fixture(_governed(tenant_aware=False), None),
    "partial": _Fixture(_partial(), AssuranceLevel.L1),
    "opaque": _Fixture(_opaque(), AssuranceLevel.L0),
}


def _open_result(**overrides: object) -> Controls:
    """Controls that let a result through, so a probe isolates one effect. A
    tenant-blind application would otherwise be (correctly) withheld, which is
    the two-tenant probe's subject, not this one's."""
    return Controls(admit_result=lambda *_: True, **overrides)  # type: ignore[arg-type]


def _serves(adapter: ForeignApplicationAdapter, tenant: str = TENANT_A) -> bool:
    try:
        adapter.run(_request(), _context(tenant))
    except Exception:
        return False
    return True


def _is_denied(adapter: ForeignApplicationAdapter, tenant: str = TENANT_A) -> bool:
    try:
        adapter.run(_request(), _context(tenant))
    except PolicyViolationError:
        return True
    except Exception:
        return False
    return False


async def _stream_texts(adapter: ForeignApplicationAdapter) -> list[str] | None:
    """The fragments a caller received, or `None` when the stream was refused."""
    try:
        return [
            step.metadata["text"] async for step in adapter.astream(_request(), _context())
        ]
    except PolicyViolationError:
        return None


def _probe_request_admission(make: Make) -> bool:
    baseline = make(controls=_open_result())
    adapter = make(controls=_open_result(admit_request=lambda *_: False))
    return _serves(baseline) and _is_denied(adapter) and adapter.app.invocations == 0


def _probe_result_admission(make: Make) -> bool:
    adapter = make(controls=Controls(admit_result=lambda *_: False))
    return _serves(make(controls=_open_result())) and (
        _is_denied(adapter) and adapter.app.invocations == 1
    )


def _probe_retrieval_blocks(make: Make) -> bool:
    adapter = make(controls=_open_result(admit_retrieval=lambda *_: False))
    return _is_denied(adapter) and adapter.app.provider_calls == []


def _probe_tool_blocks(make: Make) -> bool:
    baseline = make(controls=_open_result())
    adapter = make(controls=_open_result(admit_tool=lambda *_: False))
    return _serves(baseline) and bool(baseline.app.tool_calls) and (
        _is_denied(adapter) and adapter.app.tool_calls == []
    )


async def _probe_chunk_blocks(make: Make) -> bool:
    baseline = await _stream_texts(make(controls=_open_result()))
    adapter = make(controls=_open_result(admit_chunk=lambda *_: False))
    return bool(baseline) and await _stream_texts(adapter) is None


def _probe_egress_path(make: Make, path: EgressPath) -> bool:
    """One probe per *path*: denying exactly this path must keep it from being
    reached, while it is reached when allowed. A shared hook proves nothing
    about its sibling (ADR-0018 §9, axis 2)."""
    baseline = make(controls=_open_result())
    if not _serves(baseline) or path.name not in baseline.app.provider_calls:
        return False
    adapter = make(
        controls=_open_result(admit_egress=lambda _t, name: name != path.name)
    )
    denied = _is_denied(adapter)
    if path.support is ControlPointSupport.ENFORCED:
        return denied and path.name not in adapter.app.provider_calls
    # OBSERVED: the call is genuinely seen, and genuinely not stopped.
    return ("egress", path.name) in adapter.controls.calls and path.name in adapter.app.provider_calls


def _probe_two_tenants(make: Make) -> bool:
    """Tenant A's verified context must never yield tenant B's content; at
    ENFORCED the framework withholds the result rather than recording a leak."""
    adapter = make()
    try:
        result = adapter.run(_request(), _context(TENANT_A))
    except PolicyViolationError:
        return True
    leaked = TENANT_B in result.text or any(TENANT_B in c.passage for c in result.citations)
    return not leaked


def _probe_audit(make: Make, profile: ApplicationProfile) -> list[str]:
    failures: list[str] = []
    floor = required_audit_events(profile.bindings, profile.egress_paths)
    served_floor = floor - {AuditEventType.RUN_FAILED}  # only a failed run can emit it
    log = AuditLog()
    if not _serves(make(controls=_open_result(), audit=log)) or not served_floor <= set(log.events):
        failures.append("audit:coverage")
    for event in sorted(served_floor):
        adapter = make(controls=_open_result(), audit=AuditLog(fail_on=frozenset({event})))
        if _serves(adapter):
            failures.append(f"audit:missing-{event.value}-releases-result")
    failed_log = AuditLog()
    _is_denied(make(controls=_open_result(admit_request=lambda *_: False), audit=failed_log))
    if AuditEventType.RUN_FAILED not in failed_log.events:
        failures.append("audit:failed-run-unrecorded")
    return failures


def _probe_closed_world(make: Make, profile: ApplicationProfile) -> bool:
    adapter = make(controls=_open_result())
    declared = {path.name for path in profile.egress_paths}
    return _serves(adapter) and set(adapter.app.provider_calls) <= declared


def collect_profile_failures(make: Make) -> list[str]:
    """Every claim the declared profile makes, checked against behaviour."""
    import asyncio

    profile = make().application_profile
    failures: list[str] = []

    def check(name: str, ok: bool) -> None:
        if not ok:
            failures.append(name)

    sync_probes = {
        ControlPoint.REQUEST_ADMISSION: _probe_request_admission,
        ControlPoint.RESULT_ADMISSION: _probe_result_admission,
        ControlPoint.RETRIEVAL_RESULT: _probe_retrieval_blocks,
        ControlPoint.TOOL_INVOCATION: _probe_tool_blocks,
    }
    for binding in profile.bindings:
        if binding.support is not ControlPointSupport.ENFORCED:
            continue
        if binding.point is ControlPoint.STREAM_CHUNK:
            check("enforced:stream_chunk", asyncio.run(_probe_chunk_blocks(make)))
        elif binding.point in sync_probes:
            check(f"enforced:{binding.point.value}", sync_probes[binding.point](make))

    for path in profile.egress_paths:
        if path.support is not ControlPointSupport.UNAVAILABLE:
            check(f"egress:{path.name}", _probe_egress_path(make, path))

    ceiling = evidence_ceiling(profile)
    if evidence_status_rank(ceiling[EvidenceKind.IDENTITY_TENANT]) > evidence_status_rank(
        EvidenceStatus.OBSERVED
    ):
        check("identity:two-tenants", _probe_two_tenants(make))
    if evidence_status_rank(ceiling[EvidenceKind.AUDIT_COMPLETION]) > evidence_status_rank(
        EvidenceStatus.OBSERVED
    ):
        failures.extend(_probe_audit(make, profile))
    check("closed-world", _probe_closed_world(make, profile))
    return failures


@pytest.mark.parametrize("name", sorted(HONEST_FIXTURES))
def test_adapter_satisfies_both_protocols(name: str) -> None:
    adapter = HONEST_FIXTURES[name].make()
    assert isinstance(adapter, DocumentEngine)
    assert isinstance(adapter, ApplicationProfileProvider)


@pytest.mark.parametrize("name", sorted(HONEST_FIXTURES))
def test_every_declared_attachment_is_backed_by_real_behaviour(name: str) -> None:
    assert collect_profile_failures(HONEST_FIXTURES[name].make) == []


@pytest.mark.parametrize(
    "name", sorted(n for n, f in HONEST_FIXTURES.items() if f.expected_level is not None)
)
def test_the_computed_level_matches_what_the_hook_surface_supports(name: str) -> None:
    fixture = HONEST_FIXTURES[name]
    adapter = fixture.make()
    adapter.run(_request(), _context())
    assert adapter.conformance_report(_context()).achieved_level is fixture.expected_level


def test_the_gate_rejects_a_profile_that_overclaims_blocking() -> None:
    failures = collect_profile_failures(_overclaiming())
    assert "enforced:retrieval_result" in failures
    assert "enforced:tool_invocation" in failures
    assert "enforced:stream_chunk" in failures
    assert "egress:completion" in failures


def test_the_gate_rejects_an_application_with_an_undeclared_egress_path() -> None:
    make = _governed(undeclared_egress=True)
    assert collect_profile_failures(make) == ["closed-world"]


def test_an_overclaiming_report_is_not_trusted_without_the_probes() -> None:
    """The ceiling caps what is *reported*; only the probes can show the
    declaration itself was true. Both halves are needed."""
    adapter = _overclaiming()()
    adapter.run(_request(), _context())
    assert adapter.conformance_report(_context()).achieved_level is AssuranceLevel.L2
    assert collect_profile_failures(_overclaiming()) != []


def test_a_denied_request_never_reaches_the_application() -> None:
    adapter = _governed()(controls=Controls(admit_request=lambda *_: False))
    assert _is_denied(adapter)
    assert adapter.app.invocations == 0


@pytest.mark.parametrize("name", ["governed", "opaque"])
def test_a_control_that_cannot_answer_denies(name: str) -> None:
    """§12: a raising control is a denial, never a silent allow."""

    def broken(*_args: object) -> bool:
        raise RuntimeError("policy backend unreachable")

    adapter = HONEST_FIXTURES[name].make(controls=Controls(admit_request=broken))
    assert _is_denied(adapter)
    assert adapter.app.invocations == 0


@pytest.mark.parametrize("name", sorted(HONEST_FIXTURES))
def test_a_missing_verified_tenant_is_refused_before_the_application_runs(name: str) -> None:
    adapter = HONEST_FIXTURES[name].make()
    with pytest.raises(PolicyViolationError):
        adapter.run(_request(), _context(tenant=None))
    assert adapter.app.invocations == 0


def test_application_supplied_identity_never_overrides_the_framework_context() -> None:
    """§10: the application's tenant claim is inert metadata under its own key,
    and the application only ever receives the verified tenant — even when the
    query itself carries a different one."""
    adapter = _governed()()
    request = EngineRequest(query=Query(text="q", tenant_id=TENANT_B))
    result = adapter.run(request, _context(TENANT_A))
    assert adapter.app.received_tenants == [TENANT_A]
    assert result.metadata["application"]["tenant_id"] == APP_CLAIMED_TENANT
    assert "tenant_id" not in result.metadata


async def test_streaming_withholds_every_fragment_once_a_chunk_is_denied() -> None:
    adapter = _governed()(controls=Controls(admit_chunk=lambda *_: False))
    assert await _stream_texts(adapter) is None


async def test_streaming_is_refused_when_the_application_does_not_stream() -> None:
    adapter = _opaque()()
    assert EngineCapability.STREAMING not in adapter.capabilities
    with pytest.raises(EngineCapabilityError):
        await _stream_texts(adapter)


def test_a_hook_the_application_ignores_lowers_the_ceiling_before_deployment() -> None:
    """A missing hook is visible in the profile, not discovered in production."""
    profile = _opaque()().application_profile
    assert profile.support_for(ControlPoint.TOOL_INVOCATION) is ControlPointSupport.UNAVAILABLE
    assert profile.uncontrolled_egress
    assert evidence_ceiling(profile)[EvidenceKind.EGRESS_DECISION] is EvidenceStatus.UNSUPPORTED


def test_one_unhooked_model_call_caps_egress_for_the_whole_profile() -> None:
    profile = _partial()().application_profile
    by_name = {path.name: path.support for path in profile.egress_paths}
    assert by_name == {
        "completion": ControlPointSupport.OBSERVED,
        "fallback": ControlPointSupport.UNAVAILABLE,
    }
    assert profile.egress_ceiling is ControlPointSupport.UNAVAILABLE


def test_a_report_never_covers_a_request_that_was_not_served() -> None:
    adapter = _governed()(controls=Controls(admit_request=lambda *_: False))
    assert _is_denied(adapter)
    report = adapter.conformance_report(_context())
    assert report.evidence_for(EvidenceKind.RETRIEVAL_PROVENANCE).status is (
        EvidenceStatus.UNSUPPORTED
    )
    assert report.achieved_level is not AssuranceLevel.L2
