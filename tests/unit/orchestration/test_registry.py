"""Characterization tests for orchestration/registry.py component wiring.

Lot 4 (docs/refactoring-plan.md): captures current behavior so it isn't
broken silently during later lots — not an endorsement of the design.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
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
    assert container.evaluator is None
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
    reg = ComponentRegistry.default()

    assert set(reg._factories["chunker"]) == {"fixed", "adaptive"}
    assert set(reg._factories["embedder"]) == {"sentence-transformers", "openai-embeddings"}
    assert set(reg._factories["indexer"]) == {"qdrant"}
    assert set(reg._factories["retriever"]) == {"vector", "hybrid"}
    assert set(reg._factories["reranker"]) == {"cross-encoder"}
    assert set(reg._factories["generator"]) == {"openai", "anthropic"}
    assert set(reg._factories["guard"]) == {"basic"}
    assert set(reg._factories["evaluator"]) == {"exact-match"}
