"""Tests for contracts/manifests.py — strict (extra="forbid") validation and
the v2 schema sections. Lot 9, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from modular_rag.contracts.manifests import ComponentConfig, EngineSelection, PipelineManifest


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
