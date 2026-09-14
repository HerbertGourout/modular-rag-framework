"""Tests for contracts/assurance.py (Lot 21, ADR-0017).

The core property under test: `ConformanceReport.achieved_level` is always a
pure function of `evidence` alone — never settable directly, never dependent
on which adapter produced the report.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.assurance import (
    AssuranceLevel,
    ConformanceReport,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    assurance_level_rank,
    classify_provenance,
    compute_achieved_level,
    evidence_status_rank,
    meets_minimum_level,
)
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.answer import Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk

_ALL_UNSUPPORTED = tuple(
    EvidenceEntry(kind, EvidenceStatus.UNSUPPORTED) for kind in EvidenceKind
)


def _evidence(**overrides: EvidenceStatus) -> tuple[EvidenceEntry, ...]:
    """Build a full 8-entry evidence tuple, all UNSUPPORTED except the
    overrides (keyed by `EvidenceKind` member name, e.g. `RETRIEVAL_PROVENANCE=...`)."""
    by_kind = dict.fromkeys(EvidenceKind, EvidenceStatus.UNSUPPORTED)
    for name, status in overrides.items():
        by_kind[EvidenceKind[name]] = status
    return tuple(EvidenceEntry(kind, status) for kind, status in by_kind.items())


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_assurance_level_rank_is_strictly_increasing() -> None:
    assert (
        assurance_level_rank(AssuranceLevel.L0)
        < assurance_level_rank(AssuranceLevel.L1)
        < assurance_level_rank(AssuranceLevel.L2)
    )


def test_evidence_status_rank_is_strictly_increasing() -> None:
    ranks = [
        evidence_status_rank(s)
        for s in (
            EvidenceStatus.UNSUPPORTED,
            EvidenceStatus.OBSERVED,
            EvidenceStatus.VERIFIED,
            EvidenceStatus.ENFORCED,
        )
    ]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == 4


# ---------------------------------------------------------------------------
# compute_achieved_level — pure, adapter-independent
# ---------------------------------------------------------------------------


def test_all_unsupported_evidence_achieves_l0() -> None:
    assert compute_achieved_level(_ALL_UNSUPPORTED) == AssuranceLevel.L0


def test_l1_requires_retrieval_provenance_and_identity_both_verified() -> None:
    """ADR-0017 §6 verbatim: "L1 requires retrieval provenance and
    identity/tenant at least VERIFIED". Codex review pass 1 (HIGH-001) found
    an earlier version of this table granting L1 on IDENTITY_TENANT=OBSERVED,
    weaker than the accepted ADR allows."""
    # Provenance alone, identity UNSUPPORTED -> L0.
    assert (
        compute_achieved_level(_evidence(RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED))
        == AssuranceLevel.L0
    )

    # Identity merely OBSERVED is explicitly NOT enough for L1 any more.
    assert (
        compute_achieved_level(
            _evidence(
                RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
                IDENTITY_TENANT=EvidenceStatus.OBSERVED,
            )
        )
        == AssuranceLevel.L0
    )

    # Both at VERIFIED -> L1.
    assert (
        compute_achieved_level(
            _evidence(
                RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
                IDENTITY_TENANT=EvidenceStatus.VERIFIED,
            )
        )
        == AssuranceLevel.L1
    )


def test_l1_is_satisfied_by_a_higher_status_than_the_minimum() -> None:
    """ENFORCED > OBSERVED for IDENTITY_TENANT must still count toward L1 —
    the requirement is a floor, not an exact match."""
    evidence = _evidence(
        RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
        IDENTITY_TENANT=EvidenceStatus.ENFORCED,
    )
    assert compute_achieved_level(evidence) == AssuranceLevel.L1


def test_l2_requires_every_governed_stage_kind_enforced() -> None:
    """ADR-0017 §6 ("egress, policy, audit completion ... at least ENFORCED")
    plus ADR-0015 §3's L2 row, which also names retrieval filtering and review
    routing among the governed stages that "can be enforced and certified"."""
    base = {
        "RETRIEVAL_PROVENANCE": EvidenceStatus.VERIFIED,
        "IDENTITY_TENANT": EvidenceStatus.ENFORCED,
        "EGRESS_DECISION": EvidenceStatus.ENFORCED,
        "POLICY_DECISION": EvidenceStatus.ENFORCED,
        "AUDIT_COMPLETION": EvidenceStatus.ENFORCED,
        "FEEDBACK_REVIEW_ROUTING": EvidenceStatus.ENFORCED,
    }
    assert compute_achieved_level(_evidence(**base)) == AssuranceLevel.L2

    # Drop just one required kind below its L2 minimum -> falls back to L1
    # (still satisfies L1's narrower requirement), not L0.
    for kind in ("EGRESS_DECISION", "AUDIT_COMPLETION", "FEEDBACK_REVIEW_ROUTING"):
        degraded = dict(base)
        degraded[kind] = EvidenceStatus.UNSUPPORTED
        assert compute_achieved_level(_evidence(**degraded)) == AssuranceLevel.L1, kind


def test_l2_is_not_granted_on_merely_observed_audit_completion() -> None:
    """The specific HIGH-001 regression: audit completion at OBSERVED used to
    satisfy L2, so a report could advertise governed-stage assurance without
    enforced stage-level audit."""
    evidence = _evidence(
        RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
        IDENTITY_TENANT=EvidenceStatus.ENFORCED,
        EGRESS_DECISION=EvidenceStatus.ENFORCED,
        POLICY_DECISION=EvidenceStatus.ENFORCED,
        AUDIT_COMPLETION=EvidenceStatus.OBSERVED,
        FEEDBACK_REVIEW_ROUTING=EvidenceStatus.ENFORCED,
    )

    assert compute_achieved_level(evidence) == AssuranceLevel.L1


def test_langgraphs_unsupported_audit_caps_it_below_l2_even_with_everything_else_enforced() -> (
    None
):
    """The concrete, real scenario this contract exists to catch: a manifest
    fully governed except for the one kind LangGraph structurally cannot
    provide (AUDIT_COMPLETION) must not silently reach L2."""
    evidence = _evidence(
        RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
        IDENTITY_TENANT=EvidenceStatus.ENFORCED,
        EGRESS_DECISION=EvidenceStatus.ENFORCED,
        POLICY_DECISION=EvidenceStatus.ENFORCED,
        AUDIT_COMPLETION=EvidenceStatus.UNSUPPORTED,
    )
    assert compute_achieved_level(evidence) == AssuranceLevel.L1


def test_a_missing_evidence_kind_is_treated_as_unsupported_not_an_error() -> None:
    """compute_achieved_level() itself is permissive about incomplete input
    (treats an absent kind as UNSUPPORTED) — completeness is enforced one
    layer up, by ConformanceReport.__post_init__ (see below), not here, so
    this pure function stays usable standalone in tests."""
    partial = (EvidenceEntry(EvidenceKind.RETRIEVAL_PROVENANCE, EvidenceStatus.VERIFIED),)
    assert compute_achieved_level(partial) == AssuranceLevel.L0


# ---------------------------------------------------------------------------
# classify_provenance — the framework-owned grounding check (HIGH-003)
# ---------------------------------------------------------------------------


def _hit(content: str = "the retrieved passage", source: str = "doc.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(doc_id="d", content=content, metadata={"source": source}),
        score=0.9,
        rank=1,
        retrieval_method=RetrievalMethod.HYBRID,
    )


def _citation_for(hit: RetrievedChunk, **overrides: object) -> Citation:
    """A citation the framework itself would have built from `hit`, unless a
    test deliberately fabricates one of the fields."""
    fields: dict[str, object] = {
        "chunk_id": hit.chunk.id,
        "source": hit.chunk.metadata.get("source", "unknown"),
        "passage": hit.chunk.content,
        "score": hit.score,
        "page": hit.chunk.page,
    }
    fields.update(overrides)
    return Citation(**fields)  # type: ignore[arg-type]


def test_classify_provenance_verified_when_every_citation_is_grounded() -> None:
    hit = _hit()
    assert classify_provenance([_citation_for(hit)], [hit]) == EvidenceStatus.VERIFIED


def test_classify_provenance_verified_for_a_truncated_passage() -> None:
    """`build_citations()` truncates long passages at a sentence boundary, so
    a grounded passage is a substring of the chunk, not necessarily equal to
    it — the check must not punish the framework's own citation builder."""
    hit = _hit(content="First sentence. Second sentence that gets cut off later.")
    truncated = _citation_for(hit, passage="First sentence.")

    assert classify_provenance([truncated], [hit]) == EvidenceStatus.VERIFIED


def test_classify_provenance_unsupported_when_there_are_no_citations() -> None:
    """A generator returning no citations at all must not yield a provenance
    claim. `Generator` requires nothing about citations, so "no citations" is
    a real, reachable case, not a defect the contract may assume away."""
    assert classify_provenance([], [_hit()]) == EvidenceStatus.UNSUPPORTED
    assert classify_provenance([], []) == EvidenceStatus.UNSUPPORTED


def test_classify_provenance_observed_when_the_cited_chunk_was_never_retrieved() -> None:
    hit = _hit()
    ghost = Citation(chunk_id="never-retrieved", source="s", passage="p", score=0.1)

    assert classify_provenance([ghost], [hit]) == EvidenceStatus.OBSERVED
    assert classify_provenance([_citation_for(hit), ghost], [hit]) == EvidenceStatus.OBSERVED


def test_classify_provenance_observed_for_a_fabricated_passage_on_a_real_chunk_id() -> None:
    """Codex review pass 2, HIGH-003: matching the chunk id is not enough. A
    generator can reuse a genuinely retrieved id while fabricating the passage
    the caller is actually shown — that must never reach VERIFIED."""
    hit = _hit(content="the real retrieved passage about RAG")
    fabricated = _citation_for(hit, passage="text that was never retrieved")

    assert classify_provenance([fabricated], [hit]) == EvidenceStatus.OBSERVED


def test_classify_provenance_observed_for_a_fabricated_source_or_page() -> None:
    """The same applies to the other displayed attribution fields."""
    hit = _hit(source="real-doc.pdf")

    assert (
        classify_provenance([_citation_for(hit, source="fabricated.pdf")], [hit])
        == EvidenceStatus.OBSERVED
    )
    assert (
        classify_provenance([_citation_for(hit, page=99)], [hit]) == EvidenceStatus.OBSERVED
    )


def test_classify_provenance_observed_for_an_empty_passage() -> None:
    """An empty passage displays no evidence at all, so it cannot be verified
    evidence — even though "" is trivially a substring of anything."""
    hit = _hit()

    assert classify_provenance([_citation_for(hit, passage="")], [hit]) == EvidenceStatus.OBSERVED


def test_classify_provenance_tolerates_whitespace_and_case_differences() -> None:
    """Formatting differences are not fabrication: the comparison normalizes
    whitespace and case, and nothing else."""
    hit = _hit(content="The Real   Retrieved\nPassage")
    reformatted = _citation_for(hit, passage="the real retrieved passage")

    assert classify_provenance([reformatted], [hit]) == EvidenceStatus.VERIFIED


def test_classify_provenance_ignores_score_differences_by_design() -> None:
    """Documented scope decision: `score` is a ranking artifact a reranker
    legitimately rewrites, not displayed provenance, so it is deliberately
    excluded from the comparison."""
    hit = _hit()

    assert (
        classify_provenance([_citation_for(hit, score=0.123)], [hit]) == EvidenceStatus.VERIFIED
    )


# ---------------------------------------------------------------------------
# ConformanceReport — achieved_level is computed, never asserted
# ---------------------------------------------------------------------------


def test_conformance_report_has_no_achieved_level_constructor_parameter() -> None:
    """The strongest form of "adapters must not assert their own achieved
    level": there is no code path by which a caller can pass achieved_level
    into the constructor at all."""
    import inspect

    params = inspect.signature(ConformanceReport.__init__).parameters
    assert "achieved_level" not in params


def test_conformance_report_achieved_level_matches_compute_achieved_level() -> None:
    evidence = _evidence(
        RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
        IDENTITY_TENANT=EvidenceStatus.VERIFIED,
    )
    report = ConformanceReport(adapter_name="test", adapter_version="0.0.0", evidence=evidence)

    assert report.achieved_level == compute_achieved_level(evidence) == AssuranceLevel.L1


def test_a_deliberately_overclaiming_report_still_computes_its_real_level() -> None:
    """Even if an adapter tried to smuggle a claim in via `detail` text, the
    computed achieved_level ignores it entirely — proof by construction that
    self-assertion has no effect on the field that matters."""
    evidence = tuple(
        EvidenceEntry(kind, EvidenceStatus.UNSUPPORTED, detail="trust me, this is L2")
        for kind in EvidenceKind
    )
    report = ConformanceReport(adapter_name="dishonest", adapter_version="0.0.0", evidence=evidence)

    assert report.achieved_level == AssuranceLevel.L0


def test_conformance_report_rejects_missing_evidence_kinds() -> None:
    incomplete = (EvidenceEntry(EvidenceKind.RETRIEVAL_PROVENANCE, EvidenceStatus.VERIFIED),)
    with pytest.raises(ConfigurationError, match="Missing"):
        ConformanceReport(adapter_name="x", adapter_version="0.0.0", evidence=incomplete)


def test_conformance_report_rejects_duplicated_evidence_kinds() -> None:
    duplicated = _ALL_UNSUPPORTED + (
        EvidenceEntry(EvidenceKind.RETRIEVAL_PROVENANCE, EvidenceStatus.VERIFIED),
    )
    with pytest.raises(ConfigurationError, match="Duplicated"):
        ConformanceReport(adapter_name="x", adapter_version="0.0.0", evidence=duplicated)


def test_conformance_report_evidence_for_returns_the_matching_entry() -> None:
    report = ConformanceReport(
        adapter_name="x", adapter_version="0.0.0", evidence=_ALL_UNSUPPORTED
    )
    entry = report.evidence_for(EvidenceKind.EGRESS_DECISION)
    assert entry.kind == EvidenceKind.EGRESS_DECISION
    assert entry.status == EvidenceStatus.UNSUPPORTED


def test_conformance_report_default_contract_and_schema_versions() -> None:
    report = ConformanceReport(
        adapter_name="x", adapter_version="0.0.0", evidence=_ALL_UNSUPPORTED
    )
    assert report.contract_version == "1.0"
    assert report.schema_version == "1.0"


# ---------------------------------------------------------------------------
# meets_minimum_level
# ---------------------------------------------------------------------------


def test_meets_minimum_level_true_when_achieved_is_higher_or_equal() -> None:
    report = ConformanceReport(
        adapter_name="x",
        adapter_version="0.0.0",
        evidence=_evidence(
            RETRIEVAL_PROVENANCE=EvidenceStatus.VERIFIED,
            IDENTITY_TENANT=EvidenceStatus.VERIFIED,
        ),
    )
    assert meets_minimum_level(report, AssuranceLevel.L0)
    assert meets_minimum_level(report, AssuranceLevel.L1)
    assert not meets_minimum_level(report, AssuranceLevel.L2)
