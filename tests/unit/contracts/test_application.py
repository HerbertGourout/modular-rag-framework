"""Unit tests for `contracts/application.py` (Lot 22; ADR-0018).

The ADR calls its §6 ceiling table normative and says it belongs in a test
rather than only in prose. These are that test, plus one regression test per
finding the two Codex review passes raised against the ADR — the rules exist
because a reviewer showed a false claim was constructible without them, so
each gets a test that constructs the claim and asserts it is refused.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.application import (
    ApplicationProfile,
    ApplicationProfileProvider,
    ControlPoint,
    ControlPointBinding,
    ControlPointSupport,
    EgressPath,
    EgressPathKind,
    ExpectedAuditEvent,
    control_point_support_rank,
    evidence_ceiling,
    required_audit_events,
)
from modular_rag.contracts.assurance import EvidenceKind, EvidenceStatus
from modular_rag.contracts.audit import AuditEventType
from modular_rag.core.errors import ConfigurationError

ENFORCED = ControlPointSupport.ENFORCED
OBSERVED = ControlPointSupport.OBSERVED
UNAVAILABLE = ControlPointSupport.UNAVAILABLE


def _bindings(**overrides: ControlPointSupport) -> tuple[ControlPointBinding, ...]:
    """Every control point at ENFORCED unless named otherwise, so a test only
    states the support it actually cares about."""
    support = dict.fromkeys(ControlPoint, ENFORCED)
    for name, value in overrides.items():
        support[ControlPoint[name.upper()]] = value
    return tuple(ControlPointBinding(point, value) for point, value in support.items())


def _audit_floor(
    bindings: tuple[ControlPointBinding, ...], paths: tuple[EgressPath, ...]
) -> tuple[ExpectedAuditEvent, ...]:
    return tuple(
        ExpectedAuditEvent(event, mandatory=True)
        for event in sorted(required_audit_events(bindings, paths))
    )


def _profile(
    bindings: tuple[ControlPointBinding, ...] | None = None,
    paths: tuple[EgressPath, ...] = (),
    *,
    events: tuple[ExpectedAuditEvent, ...] | None = None,
    fingerprint: str = "sha256:deadbeef",
) -> ApplicationProfile:
    resolved = _bindings() if bindings is None else bindings
    return ApplicationProfile(
        application_name="pilot",
        application_version="1.0.0",
        adapter_version="0.1.0",
        integration_fingerprint=fingerprint,
        bindings=resolved,
        egress_paths=paths,
        expected_audit_events=_audit_floor(resolved, paths) if events is None else events,
    )


# --------------------------------------------------------------------------
# Invariant 1-2 — bindings are total, duplicate-free, and the two the adapter
# owns are never UNAVAILABLE.
# --------------------------------------------------------------------------


def test_a_profile_with_every_control_point_bound_is_valid() -> None:
    assert _profile().support_for(ControlPoint.STREAM_CHUNK) is ENFORCED


def test_a_profile_missing_a_control_point_is_rejected() -> None:
    partial = tuple(b for b in _bindings() if b.point is not ControlPoint.STREAM_CHUNK)
    with pytest.raises(ConfigurationError, match="exactly one ControlPointBinding"):
        _profile(partial)


def test_a_profile_binding_the_same_control_point_twice_is_rejected() -> None:
    doubled = (*_bindings(), ControlPointBinding(ControlPoint.STREAM_CHUNK, OBSERVED))
    with pytest.raises(ConfigurationError, match="Duplicated"):
        _profile(doubled)


@pytest.mark.parametrize(
    "point", [ControlPoint.REQUEST_ADMISSION, ControlPoint.RESULT_ADMISSION]
)
def test_the_two_structurally_owned_points_cannot_be_unavailable(point: ControlPoint) -> None:
    with pytest.raises(ConfigurationError, match="cannot exist"):
        _profile(_bindings(**{point.name.lower(): UNAVAILABLE}))


# --------------------------------------------------------------------------
# Invariant 3 — egress paths are a closed world with per-path support.
# --------------------------------------------------------------------------


def test_two_egress_paths_cannot_share_a_name() -> None:
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
        EgressPath("chat", EgressPathKind.TOOL, ControlPoint.TOOL_INVOCATION, ENFORCED),
    )
    with pytest.raises(ConfigurationError, match="unique name"):
        _profile(paths=paths)


def test_a_path_cannot_claim_more_support_than_its_control_point_offers() -> None:
    bindings = _bindings(pre_model_egress=OBSERVED)
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
    )
    with pytest.raises(ConfigurationError, match="cannot block this path"):
        _profile(bindings, paths)


def test_an_unattached_path_must_declare_itself_unavailable() -> None:
    paths = (EgressPath("chat", EgressPathKind.MODEL, None, OBSERVED),)
    with pytest.raises(ConfigurationError, match="declares no control point"):
        _profile(paths=paths)


# --------------------------------------------------------------------------
# Invariant 4 — the audit floor is derived, not chosen (Codex pass-2 HIGH-004).
# --------------------------------------------------------------------------


def test_the_audit_floor_always_covers_the_request_and_both_outcomes() -> None:
    assert required_audit_events(_bindings(), ()) >= {
        AuditEventType.QUERY_RECEIVED,
        AuditEventType.RUN_SUCCEEDED,
        AuditEventType.RUN_FAILED,
    }


def test_a_failed_run_cannot_go_unaudited() -> None:
    assert AuditEventType.RUN_FAILED in required_audit_events(_bindings(), ())


def test_retrieval_visibility_requires_auditing_retrieval() -> None:
    assert AuditEventType.RETRIEVAL_PERFORMED in required_audit_events(_bindings(), ())
    without = required_audit_events(_bindings(retrieval_result=UNAVAILABLE), ())
    assert AuditEventType.RETRIEVAL_PERFORMED not in without


def test_a_declared_model_path_requires_auditing_generation_and_egress() -> None:
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
    )
    derived = required_audit_events(_bindings(), paths)
    assert AuditEventType.GENERATION_PERFORMED in derived
    assert AuditEventType.EGRESS_DECISION in derived


def test_an_unattached_path_requires_no_egress_audit_event() -> None:
    paths = (EgressPath("chat", EgressPathKind.MODEL, None, UNAVAILABLE),)
    assert AuditEventType.EGRESS_DECISION not in required_audit_events(_bindings(), paths)


def test_guard_decision_is_required_only_when_an_admission_point_enforces() -> None:
    assert AuditEventType.GUARD_DECISION in required_audit_events(_bindings(), ())
    relaxed = _bindings(request_admission=OBSERVED, result_admission=OBSERVED)
    assert AuditEventType.GUARD_DECISION not in required_audit_events(relaxed, ())


def test_the_reviewers_counter_example_cannot_be_constructed() -> None:
    """Codex pass-2 HIGH-004, verbatim: a profile declaring only
    `RUN_SUCCEEDED` must not be buildable, because it could otherwise pass a
    full-coverage probe and reach AUDIT_COMPLETION=ENFORCED while omitting
    retrieval, generation, policy and egress entirely."""
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
    )
    with pytest.raises(ConfigurationError, match="Missing"):
        _profile(
            paths=paths,
            events=(ExpectedAuditEvent(AuditEventType.RUN_SUCCEEDED, mandatory=True),),
        )


def test_a_derived_event_cannot_be_demoted_to_optional() -> None:
    bindings = _bindings()
    demoted = tuple(
        ExpectedAuditEvent(
            event.event_type,
            mandatory=event.event_type is not AuditEventType.RUN_FAILED,
        )
        for event in _audit_floor(bindings, ())
    )
    with pytest.raises(ConfigurationError, match="not mandatory"):
        _profile(bindings, events=demoted)


def test_optional_events_above_the_floor_are_allowed() -> None:
    bindings = _bindings(retrieval_result=UNAVAILABLE)
    extra = (
        *_audit_floor(bindings, ()),
        ExpectedAuditEvent(AuditEventType.RETRIEVAL_PERFORMED, mandatory=False),
    )
    assert _profile(bindings, events=extra).expected_audit_events == extra


def test_the_same_audit_event_cannot_be_declared_twice() -> None:
    bindings = _bindings()
    doubled = (*_audit_floor(bindings, ()), ExpectedAuditEvent(AuditEventType.RUN_FAILED, True))
    with pytest.raises(ConfigurationError, match="must not repeat"):
        _profile(bindings, events=doubled)


# --------------------------------------------------------------------------
# Invariant 5 — reproducibility.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_profile_without_an_integration_fingerprint_is_rejected(blank: str) -> None:
    with pytest.raises(ConfigurationError, match="integration_fingerprint"):
        _profile(fingerprint=blank)


# --------------------------------------------------------------------------
# Egress coverage — per path, weakest wins (Codex pass-2 HIGH-002).
# --------------------------------------------------------------------------


def test_an_empty_egress_declaration_earns_no_enforcement_claim() -> None:
    profile = _profile()
    assert profile.egress_ceiling is UNAVAILABLE
    assert profile.uncontrolled_egress is False


def test_a_fully_bound_egress_declaration_is_controlled() -> None:
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
        EgressPath("search", EgressPathKind.TOOL, ControlPoint.TOOL_INVOCATION, ENFORCED),
    )
    profile = _profile(paths=paths)
    assert profile.egress_ceiling is ENFORCED
    assert profile.uncontrolled_egress is False


def test_one_unbound_path_makes_the_whole_declaration_uncontrolled() -> None:
    """Two paths through the same hook are two attachments: intercepting most
    egress is not intercepting egress."""
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
        EgressPath("summarise", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, OBSERVED),
    )
    profile = _profile(paths=paths)
    assert profile.egress_ceiling is OBSERVED
    assert profile.uncontrolled_egress is True
    assert evidence_ceiling(profile)[EvidenceKind.EGRESS_DECISION] is EvidenceStatus.VERIFIED


def test_a_second_provider_reached_by_an_unattached_tool_forbids_an_egress_claim() -> None:
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
        EgressPath("translate", EgressPathKind.TOOL, None, UNAVAILABLE),
    )
    profile = _profile(paths=paths)
    assert profile.uncontrolled_egress is True
    assert evidence_ceiling(profile)[EvidenceKind.EGRESS_DECISION] is EvidenceStatus.UNSUPPORTED


# --------------------------------------------------------------------------
# §6's normative ceiling table.
# --------------------------------------------------------------------------


def test_every_evidence_kind_has_a_ceiling() -> None:
    assert set(evidence_ceiling(_profile())) == set(EvidenceKind)


def test_admission_alone_never_proves_tenant_isolation() -> None:
    """Codex pass-1 HIGH-003: rejecting a request before the application sees
    it proves the adapter can refuse, not that the foreign retriever honours
    the trusted tenant."""
    blind = _profile(_bindings(retrieval_result=UNAVAILABLE))
    assert evidence_ceiling(blind)[EvidenceKind.IDENTITY_TENANT] is EvidenceStatus.OBSERVED


def test_tenant_enforcement_needs_retrieval_visibility_and_result_admission() -> None:
    ceiling = evidence_ceiling(_profile())
    assert ceiling[EvidenceKind.IDENTITY_TENANT] is EvidenceStatus.ENFORCED
    weaker = _profile(_bindings(result_admission=OBSERVED))
    assert evidence_ceiling(weaker)[EvidenceKind.IDENTITY_TENANT] is EvidenceStatus.VERIFIED


def test_usage_cost_can_never_be_enforced() -> None:
    """There is no stage to block, so no profile may reach ENFORCED."""
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
    )
    for profile in (_profile(), _profile(paths=paths)):
        assert evidence_ceiling(profile)[EvidenceKind.USAGE_COST] is not EvidenceStatus.ENFORCED


def test_usage_cost_is_verified_only_when_the_framework_owns_every_model_call() -> None:
    paths = (
        EgressPath("chat", EgressPathKind.MODEL, ControlPoint.PRE_MODEL_EGRESS, ENFORCED),
    )
    assert evidence_ceiling(_profile(paths=paths))[EvidenceKind.USAGE_COST] is (
        EvidenceStatus.VERIFIED
    )
    assert evidence_ceiling(_profile())[EvidenceKind.USAGE_COST] is EvidenceStatus.OBSERVED


def test_an_application_that_streams_past_the_adapter_supports_no_prevalidation() -> None:
    blind = _profile(_bindings(stream_chunk=UNAVAILABLE))
    assert evidence_ceiling(blind)[EvidenceKind.STREAMING_PREVALIDATION] is (
        EvidenceStatus.UNSUPPORTED
    )


def test_an_opaque_application_reaches_only_the_weakest_ceilings() -> None:
    """Everything the adapter does not own is UNAVAILABLE; only the two
    structurally guaranteed points remain, at OBSERVED."""
    opaque = _profile(
        _bindings(
            request_admission=OBSERVED,
            result_admission=OBSERVED,
            retrieval_result=UNAVAILABLE,
            pre_model_egress=UNAVAILABLE,
            tool_invocation=UNAVAILABLE,
            stream_chunk=UNAVAILABLE,
        )
    )
    ceiling = evidence_ceiling(opaque)
    assert ceiling[EvidenceKind.IDENTITY_TENANT] is EvidenceStatus.OBSERVED
    assert ceiling[EvidenceKind.EGRESS_DECISION] is EvidenceStatus.UNSUPPORTED
    assert ceiling[EvidenceKind.STREAMING_PREVALIDATION] is EvidenceStatus.UNSUPPORTED
    assert EvidenceStatus.ENFORCED not in ceiling.values()


def test_support_ranks_are_strictly_increasing() -> None:
    ranks = [control_point_support_rank(s) for s in (UNAVAILABLE, OBSERVED, ENFORCED)]
    assert ranks == sorted(set(ranks))


# --------------------------------------------------------------------------
# The provider Protocol.
# --------------------------------------------------------------------------


def test_an_object_exposing_the_property_satisfies_the_provider_protocol() -> None:
    class _Adapter:
        @property
        def application_profile(self) -> ApplicationProfile:
            return _profile()

    assert isinstance(_Adapter(), ApplicationProfileProvider)


def test_an_object_without_the_property_does_not_satisfy_it() -> None:
    assert not isinstance(object(), ApplicationProfileProvider)
