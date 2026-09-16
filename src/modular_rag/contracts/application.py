"""Existing-application adapter boundary (Lot 22; ADR-0018, Accepted 2026-09-16).

Describes *where the framework may intervene inside an application it does not
own*, which `contracts/engine.py` cannot express: both adapters shipped today
are framework-owned, so the framework decides where every governed stage sits
and can always place a control there. A third-party application inverts that —
a control exists only where the application happens to expose a structural
hook.

Vendor-neutral by construction, same discipline as `contracts/egress.py`
(ADR-0016) and `contracts/assurance.py` (ADR-0017): no LangChain, LangGraph,
OpenAI, Anthropic or any other vendor name may appear in a public signature
(CLAUDE.md §07). Imports `core/` plus the two sibling contracts whose
vocabulary this module references rather than redefines (`AuditEventType`,
`EvidenceKind`/`EvidenceStatus`) — the same contracts-to-contracts direction
`engine.py` already takes to `assurance.py`.

This module adds **no second execution port**. An existing-application adapter
implements the existing `DocumentEngine`; `ApplicationProfileProvider` below is
introspection only, never consulted on the request path (ADR-0018 §1-§2).

Three concepts stay separate, and nothing here blurs them (ADR-0018 §8):

- *startup capability* — may this deployment declare `assurance.min_level: X`?
  The ceiling computed here is one input to that gate, and proves nothing
  about enforcement;
- *behavioural conformance* — does a denied control actually stop a request?
  Only `tests/contract/` can answer that;
- *per-request evidence* — what was true for one request? That is
  `DocumentEngine.conformance_report(context)`.

`compute_achieved_level()` (ADR-0017) is untouched and never learns that
profiles exist: the ceiling applies per `EvidenceEntry` *before* the evidence
tuple is built, so a level stays a pure function of final normalized evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from modular_rag.contracts.assurance import EvidenceKind, EvidenceStatus
from modular_rag.contracts.audit import AuditEventType
from modular_rag.core.errors import ConfigurationError

APPLICATION_CONTRACT_VERSION = "1.0"


class ControlPoint(StrEnum):
    """Where a framework-owned control can attach to a foreign application.

    Only `REQUEST_ADMISSION` and `RESULT_ADMISSION` are structurally
    guaranteed: the adapter owns the call itself, so it runs before and after
    the application by construction. Every other member exists only if the
    application exposes a hook for it — a callback, middleware, event or
    interface it genuinely offers, never something inferred from observed
    behaviour, log parsing or heuristics (ADR-0018 §3).
    """

    REQUEST_ADMISSION = "request_admission"
    RETRIEVAL_RESULT = "retrieval_result"
    PRE_MODEL_EGRESS = "pre_model_egress"
    TOOL_INVOCATION = "tool_invocation"
    STREAM_CHUNK = "stream_chunk"
    RESULT_ADMISSION = "result_admission"


_STRUCTURALLY_PRESENT: frozenset[ControlPoint] = frozenset(
    {ControlPoint.REQUEST_ADMISSION, ControlPoint.RESULT_ADMISSION}
)


class ControlPointSupport(StrEnum):
    """How firmly a control attaches.

    Deliberately *not* `EvidenceStatus` reused: that grades a claim about a
    request that ran, this grades the integration surface independent of any
    request. `VERIFIED` has no meaning for an attachment point, and a
    four-value enum with one meaningless member invites misuse (ADR-0018 §4).
    """

    UNAVAILABLE = "unavailable"
    OBSERVED = "observed"
    ENFORCED = "enforced"


_CONTROL_POINT_SUPPORT_RANK: dict[ControlPointSupport, int] = {
    ControlPointSupport.UNAVAILABLE: 0,
    ControlPointSupport.OBSERVED: 1,
    ControlPointSupport.ENFORCED: 2,
}


def control_point_support_rank(support: ControlPointSupport) -> int:
    """Strictly-increasing rank, the `assurance_level_rank()` /
    `evidence_status_rank()` / `classification_rank()` pattern reused rather
    than reinvented (CLAUDE.md §05: "extend, don't rewrite")."""
    return _CONTROL_POINT_SUPPORT_RANK[support]


class EgressPathKind(StrEnum):
    """What kind of outbound call a declared path is."""

    MODEL = "model"
    TOOL = "tool"
    RETRIEVAL_BACKEND = "retrieval_backend"


@dataclass(frozen=True)
class EgressPath:
    """One provider-reaching call the application makes, and how firmly *this
    path* is attached.

    `support` is per path, not per control point (ADR-0018 §5). Two model
    calls reached through the same `PRE_MODEL_EGRESS` hook are two
    attachments: a hook that genuinely intercepts the first and misses the
    second is `ENFORCED` on one and weaker on the other, and neither inherits
    the other's proof.
    """

    name: str
    kind: EgressPathKind
    control_point: ControlPoint | None
    support: ControlPointSupport


@dataclass(frozen=True)
class ControlPointBinding:
    """One control point's support for this integration. `detail` is
    content-free, the discipline `EgressDecision.reason` (ADR-0016) and
    `EvidenceEntry.detail` (ADR-0017) already established."""

    point: ControlPoint
    support: ControlPointSupport
    detail: str | None = None


@dataclass(frozen=True)
class ExpectedAuditEvent:
    """One audit event this integration is expected to record. `mandatory`
    means failing to persist it blocks release of the result."""

    event_type: AuditEventType
    mandatory: bool


def required_audit_events(
    bindings: tuple[ControlPointBinding, ...],
    egress_paths: tuple[EgressPath, ...],
) -> frozenset[AuditEventType]:
    """The audit events an integration of THIS declared shape must record.

    A pure function of two fields `ApplicationProfile` already carries, so
    `__post_init__` can call it — never of the adapter's opinion about what is
    worth auditing. This is the floor `expected_audit_events` must cover: an
    adapter may add optional events above it and may never declare below it.

    Deliberately takes no `EngineCapability` set. None of the five shipped
    capabilities (streaming, cancellation, tool use, multi-turn, governance
    intercept) implies an `AuditEventType` the bindings and egress paths do
    not already imply, and a parameter the derivation never reads could not be
    supplied by a frozen dataclass that has no such field (Codex pass-2
    `HIGH-005`, which caught exactly that in the ADR's first accepted wording).

    Why derived rather than declared: letting the adapter choose its own
    denominator meant a profile declaring only `RUN_SUCCEEDED` could pass a
    full-coverage probe and reach `AUDIT_COMPLETION=ENFORCED` — the status L2
    requires — while omitting retrieval, generation, policy and egress
    entirely (Codex pass-2 `HIGH-004`).
    """
    by_point = {binding.point: binding.support for binding in bindings}

    def attached(point: ControlPoint) -> bool:
        return control_point_support_rank(
            by_point.get(point, ControlPointSupport.UNAVAILABLE)
        ) > control_point_support_rank(ControlPointSupport.UNAVAILABLE)

    def enforced(point: ControlPoint) -> bool:
        return by_point.get(point) is ControlPointSupport.ENFORCED

    # Always: the adapter owns the call (invariant 2), so it sees the request
    # and both outcomes. RUN_FAILED is required alongside RUN_SUCCEEDED so a
    # failed run cannot go unaudited.
    required = {
        AuditEventType.QUERY_RECEIVED,
        AuditEventType.RUN_SUCCEEDED,
        AuditEventType.RUN_FAILED,
    }
    if attached(ControlPoint.RETRIEVAL_RESULT):
        required.add(AuditEventType.RETRIEVAL_PERFORMED)
    if any(path.kind is EgressPathKind.MODEL for path in egress_paths):
        required.add(AuditEventType.GENERATION_PERFORMED)
    if enforced(ControlPoint.REQUEST_ADMISSION) or enforced(ControlPoint.RESULT_ADMISSION):
        required.add(AuditEventType.GUARD_DECISION)
    if any(
        path.control_point is not None
        and control_point_support_rank(path.support)
        > control_point_support_rank(ControlPointSupport.UNAVAILABLE)
        for path in egress_paths
    ):
        required.add(AuditEventType.EGRESS_DECISION)
    return frozenset(required)


@dataclass(frozen=True)
class ApplicationProfile:
    """The declared integration surface of one wrapped application.

    Total and closed by construction: five invariants are checked in
    `__post_init__` so a malformed profile cannot exist, the same discipline
    `ConformanceReport.__post_init__` already applies to `evidence`. Omission
    is the failure mode every one of them closes.
    """

    application_name: str
    application_version: str
    adapter_version: str
    integration_fingerprint: str
    bindings: tuple[ControlPointBinding, ...]
    egress_paths: tuple[EgressPath, ...]
    expected_audit_events: tuple[ExpectedAuditEvent, ...]
    schema_version: str = APPLICATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        self._check_bindings()
        self._check_egress_paths()
        self._check_expected_audit_events()
        if not self.integration_fingerprint.strip():
            raise ConfigurationError(
                "ApplicationProfile.integration_fingerprint must be a non-empty, reproducible "
                "digest over the inputs that can change this profile (application version, "
                "adapter version, which hooks the deployment enabled, and the configuration "
                "selecting them). Without it a conformance report cannot be tied to the "
                "configuration that produced it."
            )

    def _check_bindings(self) -> None:
        points = [binding.point for binding in self.bindings]
        if len(points) != len(ControlPoint) or set(points) != set(ControlPoint):
            missing = sorted(set(ControlPoint) - set(points))
            duplicated = sorted({p for p in points if points.count(p) > 1})
            raise ConfigurationError(
                "ApplicationProfile.bindings must carry exactly one ControlPointBinding per "
                f"ControlPoint. Missing: {missing}. Duplicated: {duplicated}."
            )
        for binding in self.bindings:
            if (
                binding.point in _STRUCTURALLY_PRESENT
                and binding.support is ControlPointSupport.UNAVAILABLE
            ):
                raise ConfigurationError(
                    f"ApplicationProfile.bindings declares {binding.point.value!r} as "
                    "UNAVAILABLE, which describes an adapter that cannot exist: the adapter "
                    "owns the call, so it runs before and after the application by "
                    "construction. This is a contract violation, not a low score."
                )

    def _check_egress_paths(self) -> None:
        names = [path.name for path in self.egress_paths]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ConfigurationError(
                "ApplicationProfile.egress_paths must have a unique name per path; a shared "
                f"name makes per-path certification ambiguous. Duplicated: {duplicated}."
            )
        by_point = {binding.point: binding.support for binding in self.bindings}
        for path in self.egress_paths:
            if path.control_point is None:
                if path.support is not ControlPointSupport.UNAVAILABLE:
                    raise ConfigurationError(
                        f"ApplicationProfile.egress_paths[{path.name!r}] declares no control "
                        f"point but claims support {path.support.value!r}. A path the adapter "
                        "cannot attach to is UNAVAILABLE."
                    )
                continue
            ceiling = by_point[path.control_point]
            if control_point_support_rank(path.support) > control_point_support_rank(ceiling):
                raise ConfigurationError(
                    f"ApplicationProfile.egress_paths[{path.name!r}] claims support "
                    f"{path.support.value!r} through control point "
                    f"{path.control_point.value!r}, whose binding is only {ceiling.value!r}. "
                    "A hook that cannot block anything cannot block this path."
                )

    def _check_expected_audit_events(self) -> None:
        declared = [event.event_type for event in self.expected_audit_events]
        duplicated = sorted({e for e in declared if declared.count(e) > 1})
        if duplicated:
            raise ConfigurationError(
                "ApplicationProfile.expected_audit_events must not repeat an AuditEventType. "
                f"Duplicated: {duplicated}."
            )
        required = required_audit_events(self.bindings, self.egress_paths)
        mandatory = {event.event_type for event in self.expected_audit_events if event.mandatory}
        missing = sorted(required - set(declared))
        demoted = sorted(required - mandatory - set(missing))
        if missing or demoted:
            raise ConfigurationError(
                "ApplicationProfile.expected_audit_events must cover every event derived from "
                "this profile's own bindings and egress paths, each declared mandatory. The "
                "adapter may add optional events above that floor and may never declare below "
                f"it. Missing: {missing}. Declared but not mandatory: {demoted}."
            )

    @property
    def egress_ceiling(self) -> ControlPointSupport:
        """The weakest `EgressPath.support` across every declared path.

        An empty declaration yields `UNAVAILABLE`: an application that
        provably reaches no provider has nothing to enforce, and must not earn
        an enforcement claim for that emptiness. Partial coverage caps at the
        weakest path — intercepting most egress is not intercepting egress.
        """
        if not self.egress_paths:
            return ControlPointSupport.UNAVAILABLE
        return min(
            (path.support for path in self.egress_paths),
            key=control_point_support_rank,
        )

    @property
    def uncontrolled_egress(self) -> bool:
        """True when any declared path is not bound to a control point this
        profile can actually block.

        Computed, never asserted: a self-declared boolean is an unverifiable
        claim about a negative and can contradict the paths listed beside it.
        An empty declaration is not "uncontrolled" — there is nothing to
        control — but it still yields an `UNAVAILABLE` `egress_ceiling`, so it
        earns no enforcement claim either.

        This makes *declared* coverage computable. It cannot prove the
        declaration is complete: a path nobody listed stays invisible to the
        type, which is why ADR-0018 §9 makes a closed-world network-isolation
        probe mandatory for every profile, including one declaring no paths.
        """
        return any(
            path.control_point is None or path.support is not ControlPointSupport.ENFORCED
            for path in self.egress_paths
        )

    def support_for(self, point: ControlPoint) -> ControlPointSupport:
        """This profile's support at `point`. Total by invariant 1, so this
        never raises for a well-formed profile."""
        for binding in self.bindings:
            if binding.point == point:
                return binding.support
        raise ConfigurationError(
            f"No ControlPointBinding for {point!r} — __post_init__ should have rejected this "
            "profile."
        )


def evidence_ceiling(profile: ApplicationProfile) -> dict[EvidenceKind, EvidenceStatus]:
    """ADR-0018 §6's normative table, as a pure function of the profile.

    The *ceiling* is the highest `EvidenceStatus` the integration surface
    permits. It never grants anything: a control point at `ENFORCED` only
    stops capping, and the framework must still have genuinely run the check
    ADR-0017 describes. The final status of an entry is

        min(status the framework actually earned, ceiling from this table)

    applied per entry, before the evidence tuple is built — which is what
    leaves `compute_achieved_level()` untouched and a pure function of final
    normalized evidence (ADR-0018 §7).
    """
    admission = profile.support_for(ControlPoint.REQUEST_ADMISSION)
    result = profile.support_for(ControlPoint.RESULT_ADMISSION)
    retrieval = profile.support_for(ControlPoint.RETRIEVAL_RESULT)
    stream = profile.support_for(ControlPoint.STREAM_CHUNK)
    egress = profile.egress_ceiling

    def ladder(
        *,
        observed_if: bool,
        verified_if: bool,
        enforced_if: bool,
    ) -> EvidenceStatus:
        """A ceiling is monotone: `VERIFIED` implies the `OBSERVED` bar was
        met, `ENFORCED` implies both. Each argument states only its own rung's
        extra requirement; the ladder below enforces the implication, so a
        malformed row cannot grant a high status on a low base."""
        if enforced_if and verified_if and observed_if:
            return EvidenceStatus.ENFORCED
        if verified_if and observed_if:
            return EvidenceStatus.VERIFIED
        if observed_if:
            return EvidenceStatus.OBSERVED
        return EvidenceStatus.UNSUPPORTED

    seen = ControlPointSupport.OBSERVED
    enforced = ControlPointSupport.ENFORCED

    def at_least(support: ControlPointSupport, minimum: ControlPointSupport) -> bool:
        return control_point_support_rank(support) >= control_point_support_rank(minimum)

    return {
        # Admission proves the adapter can refuse; it proves nothing about
        # whether the foreign retriever honours the trusted tenant once the
        # request is accepted. Hence retrieval visibility for VERIFIED, and
        # the ability to withhold an out-of-scope result for ENFORCED.
        EvidenceKind.IDENTITY_TENANT: ladder(
            observed_if=at_least(admission, seen),
            verified_if=admission is enforced and at_least(retrieval, seen),
            enforced_if=result is enforced,
        ),
        EvidenceKind.RETRIEVAL_PROVENANCE: ladder(
            observed_if=at_least(result, seen),
            verified_if=at_least(retrieval, seen),
            enforced_if=result is enforced,
        ),
        EvidenceKind.EGRESS_DECISION: ladder(
            observed_if=at_least(egress, seen),
            verified_if=at_least(egress, seen),
            enforced_if=egress is enforced,
        ),
        EvidenceKind.POLICY_DECISION: ladder(
            observed_if=at_least(admission, seen),
            verified_if=at_least(admission, seen),
            enforced_if=admission is enforced and result is enforced,
        ),
        # The coverage half of this claim is guaranteed structurally: the
        # profile cannot under-declare its expected events (invariant 4). What
        # remains for the ceiling is whether the adapter can see both ends of
        # the request, and whether it can block on a failed write.
        EvidenceKind.AUDIT_COMPLETION: ladder(
            observed_if=at_least(admission, seen) and at_least(result, seen),
            verified_if=at_least(admission, seen) and at_least(result, seen),
            enforced_if=result is enforced,
        ),
        # Never ENFORCED, whatever the profile: there is no stage to block.
        # Cost is reported by the application (OBSERVED) or measured by a
        # framework-owned model call (VERIFIED).
        EvidenceKind.USAGE_COST: ladder(
            observed_if=at_least(result, seen),
            verified_if=egress is enforced,
            enforced_if=False,
        ),
        EvidenceKind.FEEDBACK_REVIEW_ROUTING: ladder(
            observed_if=at_least(result, seen),
            verified_if=at_least(result, seen),
            enforced_if=result is enforced,
        ),
        EvidenceKind.STREAMING_PREVALIDATION: ladder(
            observed_if=at_least(stream, seen),
            verified_if=at_least(stream, seen),
            enforced_if=stream is enforced,
        ),
    }


@runtime_checkable
class ApplicationProfileProvider(Protocol):
    """Implemented *in addition to* `DocumentEngine` by an adapter wrapping an
    application the framework does not own.

    Introspection only: it executes nothing, and no request-path caller
    consults it. This is not a second execution port — it has no run/stream
    surface, and `DocumentEngine` is unchanged, so no shipped adapter,
    conformance fixture or caller moves (ADR-0018 §2, Option B).

    The profile is a property of the integration, not of a request, which is
    why this is a plain property while `conformance_report(context)` is
    per-request. It is read once at startup, in the composition root, at the
    first point an adapter instance exists — `registry.wire()` runs earlier
    and has no adapter to introspect (ADR-0018 §14).
    """

    @property
    def application_profile(self) -> ApplicationProfile: ...


__all__ = [
    "APPLICATION_CONTRACT_VERSION",
    "ApplicationProfile",
    "ApplicationProfileProvider",
    "ControlPoint",
    "ControlPointBinding",
    "ControlPointSupport",
    "EgressPath",
    "EgressPathKind",
    "ExpectedAuditEvent",
    "control_point_support_rank",
    "evidence_ceiling",
    "required_audit_events",
]
