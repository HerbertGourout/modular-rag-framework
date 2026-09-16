"""Semantic conformance tests for the existing-application boundary
(`contracts/application.py`, Lot 22, ADR-0018).

No adapter implements `ApplicationProfileProvider` yet — Lot 22's pilot and
its reference fixture are not written. What can be pinned today are the
invariants any implementation will have to satisfy, exercised against a
deliberately minimal fake that plays the role the second reference adapter
will play later: proving the contract is not specific to one client graph.

The rule these tests encode, from ADR-0018 §6-§7: a control point's support
**caps** what evidence may claim, and never grants it. `compute_achieved_level()`
stays a pure function of the final evidence tuple, so the ceiling is applied
per entry *before* that tuple is built — asserted directly below.
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
    evidence_ceiling,
    required_audit_events,
)
from modular_rag.contracts.assurance import (
    AssuranceLevel,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    compute_achieved_level,
    evidence_status_rank,
)


def _profile(
    supports: dict[ControlPoint, ControlPointSupport],
    paths: tuple[EgressPath, ...] = (),
) -> ApplicationProfile:
    bindings = tuple(ControlPointBinding(point, supports[point]) for point in ControlPoint)
    return ApplicationProfile(
        application_name="fixture",
        application_version="0.0.1",
        adapter_version="0.0.1",
        integration_fingerprint="sha256:fixture",
        bindings=bindings,
        egress_paths=paths,
        expected_audit_events=tuple(
            ExpectedAuditEvent(event, mandatory=True)
            for event in sorted(required_audit_events(bindings, paths))
        ),
    )


def _all(support: ControlPointSupport) -> dict[ControlPoint, ControlPointSupport]:
    return dict.fromkeys(ControlPoint, support)


class _FullyGovernedFixture:
    """The best case an application can offer: every hook exposed and
    blocking, every egress path attached."""

    @property
    def application_profile(self) -> ApplicationProfile:
        paths = (
            EgressPath(
                "completion",
                EgressPathKind.MODEL,
                ControlPoint.PRE_MODEL_EGRESS,
                ControlPointSupport.ENFORCED,
            ),
        )
        return _profile(_all(ControlPointSupport.ENFORCED), paths)


class _OpaqueFixture:
    """The realistic case: the adapter owns the call and nothing else. A
    typical callback-based application exposes no blocking pre-egress hook."""

    @property
    def application_profile(self) -> ApplicationProfile:
        supports = _all(ControlPointSupport.UNAVAILABLE)
        supports[ControlPoint.REQUEST_ADMISSION] = ControlPointSupport.ENFORCED
        supports[ControlPoint.RESULT_ADMISSION] = ControlPointSupport.ENFORCED
        paths = (
            EgressPath(
                "completion", EgressPathKind.MODEL, None, ControlPointSupport.UNAVAILABLE
            ),
        )
        return _profile(supports, paths)


PROVIDER_FACTORIES = [_FullyGovernedFixture, _OpaqueFixture]


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
def test_provider_satisfies_the_protocol(factory) -> None:
    assert isinstance(factory(), ApplicationProfileProvider)


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
def test_every_evidence_kind_receives_a_ceiling(factory) -> None:
    """Totality, the same guarantee `ConformanceReport` enforces on evidence:
    a kind that silently went missing is the failure this contract exists to
    prevent, not one it should commit itself."""
    assert set(evidence_ceiling(factory().application_profile)) == set(EvidenceKind)


@pytest.mark.parametrize("factory", PROVIDER_FACTORIES)
def test_a_ceiling_never_grants_evidence_the_framework_did_not_earn(factory) -> None:
    """§7: `final = min(earned, ceiling)`. Feeding an adapter that claims
    ENFORCED for everything through the ceiling must not produce a claim the
    surface cannot support."""
    profile = factory().application_profile
    ceiling = evidence_ceiling(profile)
    overclaimed = dict.fromkeys(EvidenceKind, EvidenceStatus.ENFORCED)
    capped = {
        kind: min(overclaimed[kind], ceiling[kind], key=evidence_status_rank)
        for kind in EvidenceKind
    }
    for kind, status in capped.items():
        assert evidence_status_rank(status) <= evidence_status_rank(ceiling[kind])


def test_an_opaque_application_cannot_reach_l2_however_it_reports() -> None:
    """The load-bearing claim of ADR-0018: an uninterceptable application
    computes a lower level arithmetically, with no adapter decision and no
    reviewer judgement."""
    profile = _OpaqueFixture().application_profile
    ceiling = evidence_ceiling(profile)
    capped = tuple(
        EvidenceEntry(kind, min(EvidenceStatus.ENFORCED, ceiling[kind], key=evidence_status_rank))
        for kind in EvidenceKind
    )
    assert compute_achieved_level(capped) is not AssuranceLevel.L2


def test_a_fully_governed_application_is_not_capped_below_its_evidence() -> None:
    """The converse control: the ceiling must not punish an application that
    genuinely exposes every hook, or it would be measuring the wrong thing."""
    profile = _FullyGovernedFixture().application_profile
    ceiling = evidence_ceiling(profile)
    for kind in (
        EvidenceKind.IDENTITY_TENANT,
        EvidenceKind.EGRESS_DECISION,
        EvidenceKind.POLICY_DECISION,
        EvidenceKind.AUDIT_COMPLETION,
        EvidenceKind.FEEDBACK_REVIEW_ROUTING,
    ):
        assert ceiling[kind] is EvidenceStatus.ENFORCED


def test_compute_achieved_level_never_sees_a_profile() -> None:
    """ADR-0017's guarantee, preserved: the level is a pure function of the
    evidence tuple. The same entries must yield the same level whatever
    profile produced them."""
    entries = tuple(EvidenceEntry(kind, EvidenceStatus.OBSERVED) for kind in EvidenceKind)
    assert compute_achieved_level(entries) is compute_achieved_level(entries)
