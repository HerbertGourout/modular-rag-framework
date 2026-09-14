"""Tests for contracts/manifests.py — strict (extra="forbid") validation and
the v2 schema sections. Lot 9, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from modular_rag.contracts.assurance import AssuranceLevel
from modular_rag.contracts.manifests import (
    AssuranceSection,
    ComponentConfig,
    EngineSelection,
    GovernanceSection,
    PipelineManifest,
)


def test_pipeline_manifest_rejects_unknown_top_level_fields() -> None:
    """Closes the gap in docs/refactoring-plan.md §2 ('Manifest configuration
    | Arbitrary config and unresolved placeholders')."""
    with pytest.raises(ValidationError, match="typo_field"):
        PipelineManifest(id="x", typo_field="oops")  # type: ignore[call-arg]


def test_component_config_rejects_unknown_fields_beside_type_and_config() -> None:
    with pytest.raises(ValidationError):
        ComponentConfig(type="fixed", unexpected="oops")  # type: ignore[call-arg]


def test_component_config_inner_config_dict_stays_free_form() -> None:
    """The forbid-extra policy applies to the manifest's own structure, not
    to a component's dynamic per-adapter config payload."""
    cfg = ComponentConfig(type="fixed", config={"anything": "goes", "here": 123})
    assert cfg.config == {"anything": "goes", "here": 123}


def test_v1_manifest_without_v2_sections_still_validates() -> None:
    manifest = PipelineManifest(id="v1-pipeline")
    assert manifest.version == "1.0"
    assert manifest.engine is None
    assert manifest.governance is None
    assert manifest.quality is None
    assert manifest.observability is None
    assert manifest.assurance is None


def test_v2_manifest_with_engine_section_validates() -> None:
    manifest = PipelineManifest(
        id="v2-pipeline",
        version="2.0",
        engine=EngineSelection(adapter="native"),
    )
    assert manifest.engine is not None
    assert manifest.engine.adapter == "native"


def test_engine_selection_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EngineSelection(adapter="native", unexpected=True)  # type: ignore[call-arg]


def test_governance_section_egress_policy_defaults_to_none() -> None:
    """Lot 20 (docs/refactoring-plan.md): additive, optional — a manifest
    with no governance.egress_policy is unaffected by this section existing."""
    governance = GovernanceSection()
    assert governance.egress_policy is None


def test_governance_section_accepts_a_configured_egress_policy() -> None:
    governance = GovernanceSection(
        egress_policy=ComponentConfig(
            type="manifest",
            config={"providers": {"openai": {"local": False, "max_classification": "internal"}}},
        )
    )
    assert governance.egress_policy is not None
    assert governance.egress_policy.type == "manifest"
    providers = governance.egress_policy.config["providers"]
    assert providers["openai"]["max_classification"] == "internal"


def test_assurance_section_min_level_defaults_to_none() -> None:
    """Lot 21 (ADR-0017, Accepted 2026-09-10): additive, optional — a
    manifest with no assurance.min_level is unaffected by this section
    existing, same optionality pattern as governance.egress_policy above."""
    assert AssuranceSection().min_level is None


def test_assurance_section_accepts_a_real_assurance_level() -> None:
    section = AssuranceSection(min_level=AssuranceLevel.L2)
    assert section.min_level == AssuranceLevel.L2


def test_assurance_section_rejects_an_unrecognized_level_at_parse_time() -> None:
    """Typed directly as AssuranceLevel (not a plain str re-validated
    later) — a typo'd level fails immediately, the same early-failure
    property every other typed manifest field already has."""
    with pytest.raises(ValidationError):
        AssuranceSection(min_level="l99")  # type: ignore[arg-type]


def test_assurance_section_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AssuranceSection(min_level=AssuranceLevel.L1, unexpected=True)  # type: ignore[call-arg]


def test_pipeline_manifest_accepts_an_assurance_section() -> None:
    manifest = PipelineManifest(
        id="assurance-pipeline",
        version="2.0",
        assurance=AssuranceSection(min_level=AssuranceLevel.L1),
    )
    assert manifest.assurance is not None
    assert manifest.assurance.min_level == AssuranceLevel.L1
