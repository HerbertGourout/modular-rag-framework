"""Characterization tests for orchestration/registry.py component wiring.

Lot 4 (docs/refactoring-plan.md): captures current behavior so it isn't
broken silently during later lots — not an endorsement of the design.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.manifests import (
    ComponentConfig,
    EngineSelection,
    GovernanceSection,
    PipelineManifest,
    QualitySection,
)
from modular_rag.core.errors import RegistryError
from modular_rag.orchestration.registry import ComponentRegistry


def _minimal_manifest(**overrides: object) -> PipelineManifest:
    defaults: dict[str, object] = {
        "id": "test-pipeline",
        "chunker": ComponentConfig(type="fake-chunker"),
        "embedder": ComponentConfig(type="fake-embedder"),
        "indexer": ComponentConfig(type="fake-indexer"),
        "retriever": ComponentConfig(type="fake-retriever"),
        "generator": ComponentConfig(type="fake-generator"),
    }
    defaults.update(overrides)
    return PipelineManifest(**defaults)  # type: ignore[arg-type]


def _fake_registry() -> ComponentRegistry:
    reg = ComponentRegistry()
    reg.register("chunker", "fake-chunker", lambda cfg: object())
    reg.register("embedder", "fake-embedder", lambda cfg: object())
    reg.register("indexer", "fake-indexer", lambda cfg: object())
    reg.register("retriever", "fake-retriever", lambda cfg: object())
    reg.register("generator", "fake-generator", lambda cfg: object())
    return reg


def test_wire_builds_the_five_required_components() -> None:
    reg = _fake_registry()

    container = reg.wire(_minimal_manifest())

    assert container.chunker is not None
    assert container.embedder is not None
    assert container.indexer is not None
    assert container.retriever is not None
    assert container.generator is not None


def test_optional_components_default_to_none_when_absent_from_manifest() -> None:
    reg = _fake_registry()

    container = reg.wire(_minimal_manifest())

    assert container.reranker is None
    assert container.guard is None
    assert container.telemetry is None


def test_unknown_component_type_raises_registry_error_listing_available_types() -> None:
    reg = _fake_registry()
    manifest = _minimal_manifest(chunker=ComponentConfig(type="does-not-exist"))

    with pytest.raises(RegistryError, match="No factory for role='chunker' type='does-not-exist'"):
        reg.wire(manifest)


def test_wire_post_injects_embedder_and_store_into_retriever_private_attrs() -> None:
    """VectorRetriever/HybridRetriever receive `_embedder`/`_store` by direct
    private-attribute assignment after construction, not via their constructor.
    Characterizes current behavior only.
    """

    class _RetrieverWithPrivateSlots:
        _embedder = None
        _store = None

    reg = _fake_registry()
    reg.register("retriever", "fake-retriever", lambda cfg: _RetrieverWithPrivateSlots())

    container = reg.wire(_minimal_manifest())

    assert container.retriever._embedder is container.embedder
    assert container.retriever._store is container.indexer


def test_registering_the_same_role_and_type_twice_silently_overwrites() -> None:
    reg = ComponentRegistry()
    reg.register("chunker", "dup", lambda cfg: "first")
    reg.register("chunker", "dup", lambda cfg: "second")

    manifest = _minimal_manifest(chunker=ComponentConfig(type="dup"))
    reg.register("embedder", "fake-embedder", lambda cfg: object())
    reg.register("indexer", "fake-indexer", lambda cfg: object())
    reg.register("retriever", "fake-retriever", lambda cfg: object())
    reg.register("generator", "fake-generator", lambda cfg: object())

    container = reg.wire(manifest)

    assert container.chunker == "second"


def test_available_types_returns_the_registered_type_names_for_a_role() -> None:
    reg = ComponentRegistry()
    reg.register("chunker", "fixed", lambda cfg: object())
    reg.register("chunker", "adaptive", lambda cfg: object())

    assert reg.available_types("chunker") == frozenset({"fixed", "adaptive"})


def test_available_types_returns_empty_frozenset_for_an_unknown_role() -> None:
    reg = ComponentRegistry()

    assert reg.available_types("does-not-exist") == frozenset()


def test_default_registry_has_the_documented_builtin_type_names() -> None:
    """Construction only — does not invoke factories, so no network/model I/O happens
    (all adapters lazy-load per CLAUDE.md rule 7). Guards against a factory silently
    disappearing or being renamed.
    """
    from modular_rag.app.default_factories import create_default_registry

    reg = create_default_registry()

    assert set(reg._factories["chunker"]) == {"fixed", "adaptive"}
    assert set(reg._factories["embedder"]) == {"sentence-transformers", "openai-embeddings"}
    assert set(reg._factories["indexer"]) == {"qdrant"}
    assert set(reg._factories["retriever"]) == {"vector", "hybrid"}
    assert set(reg._factories["reranker"]) == {"cross-encoder"}
    assert set(reg._factories["generator"]) == {"openai", "anthropic"}
    assert set(reg._factories["guard"]) == {"basic"}
    assert set(reg._factories["tenant_policy"]) == {"tenant-isolation"}
    assert set(reg._factories["policy_engine"]) == {"inline"}
    assert set(reg._factories["redactor"]) == {"patterns"}
    assert set(reg._factories["review_queue"]) == {"human-review"}
    assert set(reg._factories["audit_sink"]) == {"in-memory", "postgres"}
    assert set(reg._factories["telemetry"]) == {"structlog", "null"}
    assert set(reg._factories["lifecycle_ledger"]) == {"in-memory", "postgres"}


def test_wire_rejects_offline_evaluation_fields_in_a_runtime_manifest() -> None:
    reg = _fake_registry()
    manifest = _minimal_manifest(
        evaluation=ComponentConfig(type="exact-match"),
        quality=QualitySection(gate=ComponentConfig(type="baseline")),
    )

    with pytest.raises(RegistryError, match="offline golden-set"):
        reg.wire(manifest)


def test_wire_rejects_langgraph_control_plane_components_it_does_not_consume() -> None:
    reg = _fake_registry()
    manifest = _minimal_manifest(
        engine=EngineSelection(adapter="langgraph"),
        governance=GovernanceSection(audit_sink=ComponentConfig(type="fake-audit")),
    )

    with pytest.raises(RegistryError, match="governance.audit_sink"):
        reg.wire(manifest)


def test_wire_rejects_a_wired_tenant_policy_with_enforcement_false() -> None:
    """Codex review finding (Lot 1, second pass): `validate_capabilities()`
    rejected this contradiction, but `ComponentRegistry.wire()` — a public
    primitive callable directly, bypassing `load_pipeline()`/`load_engine()`/
    `load_application()` and their `_raise_for_manifest_errors()` call —
    only ran `runtime_manifest_errors()`, which didn't check tenant
    invariants at all. Before this fix, this exact manifest wired
    successfully and actively enforced isolation despite
    `tenant_enforcement=False` claiming otherwise."""
    reg = _fake_registry()
    reg.register("tenant_policy", "fake-tenant-policy", lambda cfg: object())
    manifest = _minimal_manifest(
        governance=GovernanceSection(
            tenant_enforcement=False,
            tenant_policy=ComponentConfig(type="fake-tenant-policy"),
        )
    )

    with pytest.raises(RegistryError, match="tenant_policy"):
        reg.wire(manifest)


def test_wire_rejects_tenant_enforcement_true_without_a_tenant_policy() -> None:
    """The inverse contradiction, same bypass: `tenant_enforcement=True` with
    no `tenant_policy` declares an intent to isolate with nothing to enforce
    it — `validate_capabilities()` caught it, direct `wire()` did not."""
    reg = _fake_registry()
    manifest = _minimal_manifest(
        governance=GovernanceSection(tenant_enforcement=True, tenant_policy=None)
    )

    with pytest.raises(RegistryError, match="tenant_enforcement=true"):
        reg.wire(manifest)


def test_postgres_audit_sink_and_lifecycle_ledger_are_manifest_activatable() -> None:
    """Registration-only check (Étape 6): these were previously Python-injectable
    only. Constructing via the factory with a `dsn` config must not require a
    live PostgreSQL connection — `psycopg` is lazy-imported inside the adapter's
    own `_get_connection()`, not at construction time."""
    from modular_rag.adapters.audit.postgres_sink import PostgresAuditSink
    from modular_rag.adapters.lifecycle.postgres_ledger import PostgresLifecycleLedger
    from modular_rag.app.default_factories import create_default_registry
    from modular_rag.contracts.manifests import ComponentConfig

    reg = create_default_registry()
    cfg = ComponentConfig(type="postgres", config={"dsn": "postgresql://localhost/test"})

    audit_sink = reg._factories["audit_sink"]["postgres"](cfg)
    ledger = reg._factories["lifecycle_ledger"]["postgres"](cfg)

    assert isinstance(audit_sink, PostgresAuditSink)
    assert isinstance(ledger, PostgresLifecycleLedger)


def test_unregistered_audit_sink_type_is_rejected_not_silently_ignored() -> None:
    """Negative test (Étape 6): an unknown audit_sink type must surface as an
    explicit capability error, not silently no-op."""
    from modular_rag.app.config_resolution import validate_capabilities
    from modular_rag.app.default_factories import create_default_registry
    from modular_rag.contracts.manifests import ComponentConfig, GovernanceSection, PipelineManifest

    reg = create_default_registry()
    manifest = PipelineManifest(
        id="x",
        governance=GovernanceSection(audit_sink=ComponentConfig(type="does-not-exist")),
    )

    errors = validate_capabilities(manifest, reg)

    assert any("audit_sink" in e and "does-not-exist" in e for e in errors)
