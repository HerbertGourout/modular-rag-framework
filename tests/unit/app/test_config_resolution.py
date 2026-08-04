"""Tests for app/config_resolution.py: interpolation, secret resolution,
precedence layering, capability validation, and v1<->v2 migration.
Lot 9, docs/refactoring-plan.md.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modular_rag.app.config_resolution import (
    EnvSecretResolver,
    interpolate,
    migrate_v1_to_v2,
    resolve_manifest,
    rollback_v2_to_v1,
    validate_capabilities,
)
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import ConfigurationError, ManifestError
from modular_rag.orchestration.registry import ComponentRegistry

# -- interpolation / secrets --------------------------------------------------


def test_interpolate_resolves_env_var_syntax(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "http://real-qdrant:6333")

    result = interpolate({"indexer": {"config": {"url": "${QDRANT_URL}"}}})

    assert result["indexer"]["config"]["url"] == "http://real-qdrant:6333"


def test_interpolate_raises_configuration_error_for_unset_env_var() -> None:
    with pytest.raises(ConfigurationError, match="NOT_SET_ANYWHERE"):
        interpolate({"url": "${NOT_SET_ANYWHERE}"})


def test_interpolate_resolves_secret_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-key")

    result = interpolate({"generator": {"config": {"api_key": "secret://OPENAI_API_KEY"}}})

    assert result["generator"]["config"]["api_key"] == "sk-real-key"


def test_env_secret_resolver_raises_configuration_error_when_unset() -> None:
    resolver = EnvSecretResolver()
    with pytest.raises(ConfigurationError, match="NOPE"):
        resolver.resolve("NOPE")


def test_interpolate_leaves_plain_strings_and_nested_lists_untouched() -> None:
    raw = {"id": "my-pipeline", "modalities": ["text", "image"], "count": 5}

    result = interpolate(raw)

    assert result == raw


# -- precedence layering ------------------------------------------------------


def test_resolve_manifest_layers_preset_then_environment_then_cli(tmp_path: Path) -> None:
    preset = tmp_path / "preset.yaml"
    preset.write_text("id: p\ndescription: from-preset\ntenant: default\n", encoding="utf-8")
    env_override = tmp_path / "env.yaml"
    env_override.write_text("tenant: env-tenant\n", encoding="utf-8")

    manifest = resolve_manifest(
        preset,
        environment_path=env_override,
        cli_overrides={"description": "from-cli"},
    )

    assert manifest.tenant == "env-tenant"  # environment layer beat preset
    assert manifest.description == "from-cli"  # cli layer beat both


def test_resolve_manifest_raises_manifest_error_on_invalid_result(tmp_path: Path) -> None:
    preset = tmp_path / "preset.yaml"
    preset.write_text("id: p\nunknown_field: oops\n", encoding="utf-8")

    with pytest.raises(ManifestError):
        resolve_manifest(preset)


# -- capability validation ----------------------------------------------------


def test_validate_capabilities_returns_empty_list_for_a_valid_manifest() -> None:
    registry = ComponentRegistry()
    for role in ("chunker", "embedder", "indexer", "retriever", "generator"):
        registry.register(role, "fake", lambda cfg: object())
    manifest = PipelineManifest(
        id="x",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )

    assert validate_capabilities(manifest, registry) == []


def test_validate_capabilities_reports_unknown_type_without_instantiating() -> None:
    registry = ComponentRegistry()  # nothing registered
    manifest = PipelineManifest(id="x")

    errors = validate_capabilities(manifest, registry)

    assert any("chunker" in e and "adaptive" in e for e in errors)


# -- v1 <-> v2 migration -------------------------------------------------------


def test_migrate_v1_to_v2_is_purely_additive() -> None:
    v1 = {"version": "1.0", "id": "my-pipeline", "tenant": "acme"}

    v2 = migrate_v1_to_v2(v1)

    assert v2["version"] == "2.0"
    assert v2["id"] == "my-pipeline"  # untouched
    assert v2["tenant"] == "acme"  # untouched
    assert v2["engine"] == {"adapter": "native", "config": {}}
    assert v2["governance"]["tenant_enforcement"] is False


def test_migrate_v1_to_v2_validates_as_a_real_manifest() -> None:
    v1 = {"version": "1.0", "id": "my-pipeline"}
    v2 = migrate_v1_to_v2(v1)

    manifest = PipelineManifest.model_validate(v2)

    assert manifest.version == "2.0"
    assert manifest.engine is not None


def test_rollback_v2_to_v1_strips_v2_sections_and_resets_version() -> None:
    v1 = {"version": "1.0", "id": "my-pipeline", "tenant": "acme"}
    v2 = migrate_v1_to_v2(v1)

    rolled_back = rollback_v2_to_v1(v2)

    assert rolled_back == v1


def test_migrate_then_rollback_round_trips_to_the_original_v1_dict(tmp_path: Path) -> None:
    original = {"version": "1.0", "id": "roundtrip-pipeline", "environment": "prod"}

    round_tripped = rollback_v2_to_v1(migrate_v1_to_v2(original))

    assert round_tripped == original
    # And both ends actually validate as real manifests, not just as dicts:
    assert PipelineManifest.model_validate(original).id == "roundtrip-pipeline"
    assert PipelineManifest.model_validate(round_tripped).id == "roundtrip-pipeline"


def test_migrate_v1_to_v2_rejects_an_unknown_version() -> None:
    with pytest.raises(ManifestError, match="Unknown manifest version"):
        migrate_v1_to_v2({"version": "99.0", "id": "x"})
