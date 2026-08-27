"""Characterization tests for app/bootstrap.py: manifest loading and pipeline wiring.

Lot 4 (docs/refactoring-plan.md).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modular_rag.app.bootstrap import (
    load_application,
    load_engine,
    load_manifest,
    load_native_engine,
    load_pipeline,
)
from modular_rag.contracts.engine import DocumentEngine
from modular_rag.core.errors import ConfigurationError, ManifestError
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter


def test_load_manifest_raises_manifest_error_when_file_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"

    with pytest.raises(ManifestError, match="Manifest not found"):
        load_manifest(missing)


def test_load_manifest_raises_manifest_error_on_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("chunker: [this is not: valid: yaml", encoding="utf-8")

    with pytest.raises(ManifestError, match="Invalid YAML"):
        load_manifest(bad)


def test_load_manifest_validates_against_pipeline_manifest_schema(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("id: my-pipeline\n", encoding="utf-8")

    manifest = load_manifest(manifest_file)

    assert manifest.id == "my-pipeline"
    assert manifest.chunker.type == "adaptive"  # documented default
    assert manifest.tenant == "default"


def test_load_pipeline_wires_the_default_registry_and_returns_a_rag_engine(
    tmp_path: Path,
) -> None:
    """Exercises ComponentRegistry.default() end to end via built-in adapter type
    names. Safe as a unit test: every adapter here lazy-loads its heavy dependency
    (sentence-transformers model, qdrant-client connection, OpenAI client) on first
    *use*, not at construction — confirmed by reading each adapter's __init__
    before writing this test. No network/model I/O happens.
    """
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        "id: my-pipeline\n"
        "chunker:\n  type: fixed\n  config:\n    chunk_size: 100\n"
        "embedder:\n  type: sentence-transformers\n  config: {}\n"
        "indexer:\n  type: qdrant\n  config: {}\n"
        "retriever:\n  type: vector\n  config: {}\n"
        "generator:\n  type: openai\n  config: {}\n",
        encoding="utf-8",
    )

    pipeline = load_pipeline(manifest_file)

    assert isinstance(pipeline, RAGEngine)
    assert pipeline.manifest_id == "my-pipeline"  # public property since Lot 8


def test_load_native_engine_wraps_the_same_wiring_as_load_pipeline(tmp_path: Path) -> None:
    """Lot 8's compatibility route: load_pipeline() is unchanged (V1 parity);
    load_native_engine() wraps the identical wire() output in the
    DocumentEngine-conformant adapter. 'Rollback' from the adapter is simply
    calling load_pipeline() instead — both start from the same wiring."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        "id: my-pipeline\n"
        "chunker:\n  type: fixed\n  config:\n    chunk_size: 100\n"
        "embedder:\n  type: sentence-transformers\n  config: {}\n"
        "indexer:\n  type: qdrant\n  config: {}\n"
        "retriever:\n  type: vector\n  config: {}\n"
        "generator:\n  type: openai\n  config: {}\n",
        encoding="utf-8",
    )

    engine = load_native_engine(manifest_file)

    assert isinstance(engine, NativeEngineAdapter)
    assert isinstance(engine, DocumentEngine)


_MINIMAL_MANIFEST = (
    "id: my-pipeline\n"
    "chunker:\n  type: fixed\n  config:\n    chunk_size: 100\n"
    "embedder:\n  type: sentence-transformers\n  config: {}\n"
    "indexer:\n  type: qdrant\n  config: {}\n"
    "retriever:\n  type: vector\n  config: {}\n"
    "generator:\n  type: openai\n  config: {}\n"
)


def test_load_engine_defaults_to_native_when_no_engine_section(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MINIMAL_MANIFEST, encoding="utf-8")

    engine = load_engine(manifest_file)

    assert isinstance(engine, NativeEngineAdapter)


def test_load_engine_selects_native_explicitly(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MINIMAL_MANIFEST + "engine:\n  adapter: native\n", encoding="utf-8")

    engine = load_engine(manifest_file)

    assert isinstance(engine, NativeEngineAdapter)


def test_load_engine_selects_langgraph(tmp_path: Path) -> None:
    """Lot 15, docs/refactoring-plan.md — the same manifest's component
    wiring, run through the second adapter instead of the first."""
    from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter

    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "engine:\n  adapter: langgraph\n", encoding="utf-8"
    )

    engine = load_engine(manifest_file)

    assert isinstance(engine, LangGraphEngineAdapter)
    assert isinstance(engine, DocumentEngine)


def test_load_application_requires_identity_is_false_without_a_tenant_policy(
    tmp_path: Path,
) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(_MINIMAL_MANIFEST, encoding="utf-8")

    application = load_application(manifest_file)

    assert application.requires_identity is False


def test_load_application_requires_identity_is_true_with_a_wired_tenant_policy(
    tmp_path: Path,
) -> None:
    """Lot 1 (tenant fail-closed): `requires_identity` reflects whether
    `Container.tenant_policy` actually gets wired — driven by
    `governance.tenant_policy`'s presence, not `governance.tenant_enforcement`'s
    value (`registry.py::wire()` wires `tenant_policy` whenever the former is
    set, regardless of the latter's boolean — see `RAGEngine.tenant_policy_active`
    and its docstring). Exercised against a real manifest + the real default
    registry, not a hand-built fake, closing the gap where only fakes proved
    this property's behavior."""
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "governance:\n"
        "  tenant_enforcement: true\n"
        "  tenant_policy:\n"
        "    type: tenant-isolation\n"
        "    config: {}\n",
        encoding="utf-8",
    )

    application = load_application(manifest_file)

    assert application.requires_identity is True


def test_load_application_with_langgraph_and_a_tracer_wires_successfully(
    tmp_path: Path,
) -> None:
    """ADR-0012, Codex review pass 1 HIGH-001: `observability.tracer` must
    not be rejected under `engine.adapter='langgraph'` — `app.request`/
    `api.answer`/`api.retrieve` spans are created by `app/application.py`/
    `api/__init__.py` directly against `Container.tracer`, independent of
    which `DocumentEngine` is selected, so the declared control is genuinely
    honored (unlike `telemetry`/`audit_sink`/`policy_engine`/`review_queue`,
    which really are never reached under LangGraph). An earlier version of
    `runtime_manifest_errors()` blanket-rejected this and made the field
    unusable with the LangGraph adapter entirely — this test loads a real
    manifest through the real default registry (not a fake) to prove the
    combination is now accepted and the tracer reaches the application
    facade. `type: otel` with no `otlp_endpoint` creates real spans without
    ever exporting them over the network (ADR-0012's own "toggleable export"
    design), so this stays a safe, no-network unit test."""
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "engine:\n  adapter: langgraph\n"
        "observability:\n  tracer:\n    type: otel\n    config: {}\n",
        encoding="utf-8",
    )

    application = load_application(manifest_file)

    assert application.tracer is not None
    assert isinstance(application.tracer, OtelTracer)


def test_load_application_with_langgraph_and_a_meter_wires_successfully(
    tmp_path: Path,
) -> None:
    """ADR-0013, following ADR-0012's own precedent exactly (see the
    tracer/langgraph test above) — loads a real manifest through the real
    default registry to prove `observability.meter` is accepted under
    `engine.adapter='langgraph'` and reaches the application facade."""
    from modular_rag.adapters.observability.otel_meter import OtelMeter

    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "engine:\n  adapter: langgraph\n"
        "observability:\n  meter:\n    type: otel\n    config: {}\n",
        encoding="utf-8",
    )

    application = load_application(manifest_file)

    assert application.meter is not None
    assert isinstance(application.meter, OtelMeter)


def test_load_engine_raises_on_an_unknown_adapter_name(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "engine:\n  adapter: some-future-engine\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="some-future-engine"):
        load_engine(manifest_file)


def test_load_pipeline_rejects_a_delegated_engine_instead_of_silently_using_native(
    tmp_path: Path,
) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        _MINIMAL_MANIFEST + "engine:\n  adapter: langgraph\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="only supports.*native"):
        load_pipeline(manifest_file)


def test_a_v1_manifest_migrated_to_v2_and_switched_to_langgraph_loads_correctly(
    tmp_path: Path,
) -> None:
    """Lot 15's "migration" acceptance bar: a real v1 manifest, migrated to
    v2 (Lot 9's migrate_v1_to_v2), with engine.adapter overridden to
    "langgraph", must be a loadable, valid configuration that selects the
    second adapter — not just a schema that happens to accept the string."""
    import yaml

    from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter
    from modular_rag.app.config_resolution import migrate_v1_to_v2

    v1 = yaml.safe_load(_MINIMAL_MANIFEST)
    v1["version"] = "1.0"
    v2 = migrate_v1_to_v2(v1)
    v2["engine"]["adapter"] = "langgraph"

    manifest_file = tmp_path / "migrated.yaml"
    manifest_file.write_text(yaml.dump(v2), encoding="utf-8")

    engine = load_engine(manifest_file)

    assert isinstance(engine, LangGraphEngineAdapter)
