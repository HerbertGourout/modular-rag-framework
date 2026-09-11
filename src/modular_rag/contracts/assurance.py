"""Engine-independent assurance contract and conformance report (Lot 21,
docs/refactoring-plan.md; ADR-0017, Accepted 2026-09-10).

Vendor-neutral by construction, same discipline as `contracts/egress.py`
(ADR-0016) and `contracts/engine.py` itself: no LangGraph, OpenAI, Anthropic,
or any other vendor name may appear in this module's public signatures
(CLAUDE.md §07). Imports only `core/`.

Makes ADR-0015 §3's L0/L1/L2 table machine-checkable rather than aspirational:
`AssuranceLevel` matches that table exactly; this module does not redefine
what the levels mean, only how an adapter reports and proves which one it
achieves for a given request. `EvidenceStatus` keeps "the adapter says so"
(`OBSERVED`) strictly distinct from "the framework's own code independently
checked it" (`VERIFIED`) and "the framework's own code can block on it"
(`ENFORCED`) — collapsing those three into one boolean is the specific
overclaim risk ADR-0015's own Consequences section named ("normalizing
evidence across engines can collapse meaningful vendor differences").

`ConformanceReport.achieved_level` is a computed property, not a constructor
parameter — there is no code path by which an adapter can pass its own
`achieved_level` into a report. `achieved_level` is always the output of
`compute_achieved_level()`, a pure function of `evidence` alone, independent
of which adapter produced it (ADR-0017 §6/§7).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.answer import Citation
from modular_rag.core.models.retrieved import RetrievedChunk

ASSURANCE_CONTRACT_VERSION = "1.0"


class AssuranceLevel(StrEnum):
    """ADR-0015 §3's three profiles, unchanged in meaning here — this module
    only makes them checkable. Ordered: `L0 < L1 < L2`, via
    `assurance_level_rank()` below."""

    L0 = "l0"  # opaque request/response
    L1 = "l1"  # evidence-aware
    L2 = "l2"  # governed stages


_ASSURANCE_LEVEL_RANK: dict[AssuranceLevel, int] = {
    AssuranceLevel.L0: 0,
    AssuranceLevel.L1: 1,
    AssuranceLevel.L2: 2,
}


def assurance_level_rank(level: AssuranceLevel) -> int:
    """Strictly-increasing rank for comparing a declared minimum level
    against a computed `achieved_level` — the `classification_rank()`
    pattern `core.enums` already established for `DataClassification`
    (ADR-0016), reused rather than reinvented (CLAUDE.md §05: "extend,
    don't rewrite")."""
    return _ASSURANCE_LEVEL_RANK[level]


class EvidenceStatus(StrEnum):
    """The three-way distinction Lot 21's required scope names explicitly:
    "observable" (the adapter can report evidence), "verifiable" (the
    framework can validate it independently), "enforceable" (the framework
    can prevent the stage from proceeding on policy failure). `UNSUPPORTED`
    is a fourth, necessary floor: the adapter has no mechanism for this kind
    at all, for this manifest wiring.

    Ordered: `UNSUPPORTED < OBSERVED < VERIFIED < ENFORCED`, via
    `evidence_status_rank()` below. `OBSERVED` must never be silently
    promoted to `VERIFIED`/`ENFORCED` by report-generation code — see each
    adapter's `conformance_report()` docstring for exactly which real,
    executed framework behavior justifies each kind's status.
    """

    UNSUPPORTED = "unsupported"
    OBSERVED = "observed"
    VERIFIED = "verified"
    ENFORCED = "enforced"


_EVIDENCE_STATUS_RANK: dict[EvidenceStatus, int] = {
    EvidenceStatus.UNSUPPORTED: 0,
    EvidenceStatus.OBSERVED: 1,
    EvidenceStatus.VERIFIED: 2,
    EvidenceStatus.ENFORCED: 3,
}


def evidence_status_rank(status: EvidenceStatus) -> int:
    return _EVIDENCE_STATUS_RANK[status]


class EvidenceKind(StrEnum):
    """The minimum useful set (ADR-0017 §4) — not claimed exhaustive. Each
    value maps onto a type that already exists elsewhere in this codebase;
    this module references those shapes, it does not redefine them:

    - IDENTITY_TENANT: `contracts.engine.ExecutionContext.tenant_id`,
      enforced by `contracts.security.TenantPolicy`.
    - RETRIEVAL_PROVENANCE: `core.models.answer.Citation`.
    - EGRESS_DECISION: `contracts.egress.EgressDecision` (ADR-0016).
    - POLICY_DECISION: `contracts.engine.GovernanceDecision` /
      `contracts.security.GuardResult`.
    - AUDIT_COMPLETION: `contracts.audit.AuditEventType` coverage.
    - USAGE_COST: generation token/cost metadata (ADR-0013's `Meter`).
    - FEEDBACK_REVIEW_ROUTING: `contracts.feedback`, `contracts.review`.
    - STREAMING_PREVALIDATION: a guard/policy check that runs, and can
      block, before any content reaches `EngineCapability.STREAMING`
      output.
    """

    IDENTITY_TENANT = "identity_tenant"
    RETRIEVAL_PROVENANCE = "retrieval_provenance"
    EGRESS_DECISION = "egress_decision"
    POLICY_DECISION = "policy_decision"
    AUDIT_COMPLETION = "audit_completion"
    USAGE_COST = "usage_cost"
    FEEDBACK_REVIEW_ROUTING = "feedback_review_routing"
    STREAMING_PREVALIDATION = "streaming_prevalidation"


@dataclass(frozen=True)
class EvidenceEntry:
    """One `EvidenceKind`'s status for one `conformance_report()` call.
    `detail` is content-free by the same discipline `EgressDecision.reason`
    (ADR-0016) already established: built only from kind/status/provider-
    shaped facts, never caller query/chunk/answer content."""

    kind: EvidenceKind
    status: EvidenceStatus
    detail: str | None = None


# The per-level required-EvidenceKind mapping, taken directly from the two
# accepted ADRs rather than chosen freely. ADR-0017 §6 fixes the minimums
# verbatim: "L2 requires every evidence kind relevant to a governed stage
# (egress, policy, audit completion) to be at least ENFORCED; L1 requires
# retrieval provenance and identity/tenant at least VERIFIED; L0 requires
# nothing beyond a report existing at all." ADR-0015 §3's L2 row adds review
# routing and retrieval filtering to the governed stages that "can be enforced
# and certified", so both appear at L2 here too.
#
# Codex review pass 1, HIGH-001: an earlier version of this table granted L1
# on IDENTITY_TENANT=OBSERVED and L2 on AUDIT_COMPLETION=OBSERVED, and omitted
# review routing from L2 entirely -- weaker than the accepted ADRs allow. That
# ADR-0017 §6 also calls the exact mapping "implementation detail" authorizes
# choosing *which* kinds map to a level, never lowering a minimum the same
# paragraph states explicitly. Restored to the accepted meanings.
_LEVEL_REQUIREMENTS: dict[AssuranceLevel, dict[EvidenceKind, EvidenceStatus]] = {
    AssuranceLevel.L0: {},
    AssuranceLevel.L1: {
        EvidenceKind.RETRIEVAL_PROVENANCE: EvidenceStatus.VERIFIED,
        EvidenceKind.IDENTITY_TENANT: EvidenceStatus.VERIFIED,
    },
    AssuranceLevel.L2: {
        EvidenceKind.RETRIEVAL_PROVENANCE: EvidenceStatus.VERIFIED,
        EvidenceKind.IDENTITY_TENANT: EvidenceStatus.ENFORCED,
        EvidenceKind.EGRESS_DECISION: EvidenceStatus.ENFORCED,
        EvidenceKind.POLICY_DECISION: EvidenceStatus.ENFORCED,
        EvidenceKind.AUDIT_COMPLETION: EvidenceStatus.ENFORCED,
        EvidenceKind.FEEDBACK_REVIEW_ROUTING: EvidenceStatus.ENFORCED,
    },
}

# Checked in descending order so the *highest* satisfied level wins — L0's
# empty requirement dict always satisfies trivially, so this loop always
# terminates with a result; it never falls through.
_LEVELS_DESCENDING = (AssuranceLevel.L2, AssuranceLevel.L1, AssuranceLevel.L0)


def compute_achieved_level(evidence: tuple[EvidenceEntry, ...]) -> AssuranceLevel:
    """Pure, adapter-independent function of `evidence` alone (ADR-0017 §6):
    no adapter identity, no self-declared level, nothing but the evidence
    entries themselves. This is the *only* place `achieved_level` is ever
    computed — `ConformanceReport.achieved_level` calls this and nothing
    else, so an adapter cannot assert a level its own evidence doesn't
    support."""
    by_kind = {entry.kind: entry.status for entry in evidence}
    for level in _LEVELS_DESCENDING:
        requirements = _LEVEL_REQUIREMENTS[level]
        if all(
            evidence_status_rank(by_kind.get(kind, EvidenceStatus.UNSUPPORTED))
            >= evidence_status_rank(min_status)
            for kind, min_status in requirements.items()
        ):
            return level
    return AssuranceLevel.L0  # unreachable (L0's empty dict always satisfies above)


def _normalized(text: str) -> str:
    """Whitespace-insensitive, case-insensitive form for comparing a citation's
    displayed passage against the chunk it claims to come from. Deliberately
    tolerant of formatting only — never of different words."""
    return " ".join(text.split()).casefold()


def _citation_is_grounded(citation: Citation, hit: RetrievedChunk) -> bool:
    """Does this citation's *displayed evidence* actually come from the chunk
    it names? (Codex review pass 2, HIGH-003.)

    Matching the chunk id alone is not enough: a generator can reuse a real
    retrieved id while fabricating the passage and source the caller is shown.
    So the passage must genuinely appear in that chunk's text, and the
    attribution fields must be the chunk's own.

    `score` is deliberately *not* compared. It is a ranking artifact rather
    than displayed provenance — a reranker legitimately rewrites it — so
    requiring equality there would downgrade honest pipelines without making
    a fabricated passage any harder to spot. Recorded as a scope decision,
    not an oversight.
    """
    passage = _normalized(citation.passage)
    if not passage or passage not in _normalized(hit.chunk.content):
        return False
    if citation.page != hit.chunk.page:
        return False
    # `generation.citations.builder.build_citations()` is the framework's own
    # citation constructor and reads exactly this key, with this default.
    # bool(): `Chunk.metadata` is `dict[str, Any]`, so the comparison is typed
    # `Any` without it (mypy no-any-return).
    return bool(citation.source == hit.chunk.metadata.get("source", "unknown"))


def classify_provenance(
    citations: Sequence[Citation], retrieved: Sequence[RetrievedChunk]
) -> EvidenceStatus:
    """The framework-owned grounding check (Codex review pass 1 HIGH-003;
    strengthened after pass 2 HIGH-003).

    One definition of "grounded", shared by every engine, so a provenance
    claim never rests on trusting a `Generator` to have produced honest
    citations — `contracts.generation.Generator` requires only that
    `generate()` return an `Answer`, saying nothing about citations at all,
    so a custom or defective generator can return none, return citations
    unrelated to what was retrieved, or — the case pass 2 caught — reuse a
    real chunk id while fabricating the passage and source actually shown to
    the caller. This function is what makes `VERIFIED` mean "the framework
    compared the evidence", not "the component asserted it":

    - `VERIFIED` — citations exist, and for every one of them the named chunk
      really was retrieved for this request *and* the displayed passage,
      source and page really are that chunk's.
    - `OBSERVED` — citations exist, but at least one names a chunk that was
      not retrieved, or presents evidence that does not match the chunk it
      names: the framework saw provenance data and could not verify it, which
      is precisely what `OBSERVED` is for.
    - `UNSUPPORTED` — no citations at all: there is nothing to observe, so
      claiming otherwise would be the original overclaim.

    Content-free in what it *emits*: it reads passage text to compare it, but
    returns only an `EvidenceStatus` — no caller content ever reaches a
    `ConformanceReport`.
    """
    if not citations:
        return EvidenceStatus.UNSUPPORTED
    by_id = {hit.chunk.id: hit for hit in retrieved}
    for citation in citations:
        hit = by_id.get(citation.chunk_id)
        if hit is None or not _citation_is_grounded(citation, hit):
            return EvidenceStatus.OBSERVED
    return EvidenceStatus.VERIFIED


@dataclass(frozen=True)
class ConformanceReport:
    """A `DocumentEngine` adapter's deterministic, machine-readable assurance
    report for one `ExecutionContext` (ADR-0017 §7).

    `achieved_level` is a computed `@property`, not a field an adapter's
    constructor call can set — see the module docstring. `evidence` must
    carry exactly one `EvidenceEntry` per `EvidenceKind` (checked in
    `__post_init__`): a report that silently omits a kind is exactly the
    kind of "supplied-but-unverified" gap this contract exists to make
    visible, not the kind it should itself commit by omission.
    """

    adapter_name: str
    adapter_version: str
    evidence: tuple[EvidenceEntry, ...]
    contract_version: str = ASSURANCE_CONTRACT_VERSION
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        kinds = [entry.kind for entry in self.evidence]
        if len(kinds) != len(EvidenceKind) or set(kinds) != set(EvidenceKind):
            missing = set(EvidenceKind) - set(kinds)
            duplicated = {k for k in kinds if kinds.count(k) > 1}
            raise ConfigurationError(
                f"ConformanceReport.evidence must carry exactly one EvidenceEntry per "
                f"EvidenceKind. Missing: {sorted(missing)}. Duplicated: {sorted(duplicated)}."
            )

    @property
    def achieved_level(self) -> AssuranceLevel:
        return compute_achieved_level(self.evidence)

    def evidence_for(self, kind: EvidenceKind) -> EvidenceEntry:
        for entry in self.evidence:
            if entry.kind == kind:
                return entry
        raise ConfigurationError(
            f"No EvidenceEntry for {kind!r} — __post_init__ should have rejected this report."
        )


def meets_minimum_level(report: ConformanceReport, minimum: AssuranceLevel) -> bool:
    """Manifest-validation helper: does `report` reach at least `minimum`?
    Trivial wrapper over `assurance_level_rank()` so callers (e.g.
    `orchestration/registry.py`) never hand-roll the comparison direction."""
    return assurance_level_rank(report.achieved_level) >= assurance_level_rank(minimum)


__all__ = [
    "ASSURANCE_CONTRACT_VERSION",
    "AssuranceLevel",
    "assurance_level_rank",
    "EvidenceStatus",
    "evidence_status_rank",
    "EvidenceKind",
    "EvidenceEntry",
    "ConformanceReport",
    "compute_achieved_level",
    "classify_provenance",
    "meets_minimum_level",
]
