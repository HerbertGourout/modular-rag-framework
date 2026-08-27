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
    ObservabilitySection,
    PipelineManifest,
    QualitySection,
)
from modular_rag.core.errors import ConfigurationError, RegistryError
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
    assert container.tracer is None


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
    assert set(reg._factories["embedder"]) == {
        "sentence-transformers",
        "openai-embeddings",
        "deterministic",
    }
    assert set(reg._factories["indexer"]) == {"qdrant"}
    assert set(reg._factories["retriever"]) == {"vector", "hybrid", "sparse-qdrant"}
    assert set(reg._factories["reranker"]) == {"cross-encoder"}
    assert set(reg._factories["generator"]) == {"openai", "anthropic", "deterministic"}
    assert set(reg._factories["guard"]) == {"basic"}
    assert set(reg._factories["tenant_policy"]) == {"tenant-isolation"}
    assert set(reg._factories["policy_engine"]) == {"inline"}
    assert set(reg._factories["redactor"]) == {"patterns"}
    assert set(reg._factories["review_queue"]) == {"human-review"}
    assert set(reg._factories["audit_sink"]) == {"in-memory", "postgres"}
    assert set(reg._factories["telemetry"]) == {"structlog", "null"}
    assert set(reg._factories["tracer"]) == {"otel", "null"}
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


def test_wire_registers_a_configured_tracer() -> None:
    """ADR-0012."""
    reg = _fake_registry()
    reg.register("tracer", "fake-tracer", lambda cfg: "a-tracer")
    manifest = _minimal_manifest(
        observability=ObservabilitySection(tracer=ComponentConfig(type="fake-tracer"))
    )

    container = reg.wire(manifest)

    assert container.tracer == "a-tracer"


def test_wire_accepts_a_tracer_under_the_langgraph_adapter() -> None:
    """ADR-0012, corrected by Codex review pass 1 HIGH-001: an earlier version
    of `runtime_manifest_errors()` blanket-rejected `observability.tracer`
    under `engine.adapter='langgraph'`, copying the `telemetry`/`audit_sink`/
    `policy_engine`/`review_queue` pattern without checking whether it
    applied for the same reason. It doesn't: unlike those four (read only
    from inside `RAGEngine`, never reached under LangGraph),
    `Container.tracer` is also read directly by `app/application.py`'s
    `"app.request"` span and `api/__init__.py`'s `"api.answer"`/
    `"api.retrieve"` spans — both engine-neutral, both unconditional on the
    selected `DocumentEngine`. Rejecting the field would have silently
    disabled spans that actually do work, contradicting ADR-0012's own
    claim that a LangGraph-routed request still gets those two root spans."""
    reg = _fake_registry()
    reg.register("tracer", "fake-tracer", lambda cfg: "a-tracer")
    manifest = _minimal_manifest(
        engine=EngineSelection(adapter="langgraph"),
        observability=ObservabilitySection(tracer=ComponentConfig(type="fake-tracer")),
    )

    container = reg.wire(manifest)

    assert container.tracer == "a-tracer"


def test_wire_registers_a_configured_meter() -> None:
    """ADR-0013."""
    reg = _fake_registry()
    reg.register("meter", "fake-meter", lambda cfg: "a-meter")
    manifest = _minimal_manifest(
        observability=ObservabilitySection(meter=ComponentConfig(type="fake-meter"))
    )

    container = reg.wire(manifest)

    assert container.meter == "a-meter"


def test_wire_accepts_a_meter_under_the_langgraph_adapter() -> None:
    """ADR-0013, following ADR-0012's own precedent (`observability.tracer`)
    exactly, applied here from the start rather than needing a corrective
    round: `Container.meter` is also read directly by `app/application.py`'s
    `mrag.request.duration`/`mrag.request.errors` recording — engine-neutral,
    unconditional on the selected `DocumentEngine` — so rejecting it under
    LangGraph would silently disable metrics that actually work."""
    reg = _fake_registry()
    reg.register("meter", "fake-meter", lambda cfg: "a-meter")
    manifest = _minimal_manifest(
        engine=EngineSelection(adapter="langgraph"),
        observability=ObservabilitySection(meter=ComponentConfig(type="fake-meter")),
    )

    container = reg.wire(manifest)

    assert container.meter == "a-meter"


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


# ---------------------------------------------------------------------------
# ADR-0009 ("VectorIndexer sub-protocol and dimension reconciliation"):
# `wire()` calls `bind_embedder()` — a real, protocol-declared VectorIndexer
# method (Codex review, second pass: an earlier version of this used
# `setattr(store, "_embedder", embedder)`, an undeclared private-attribute
# convention nothing in the Protocol required an implementation to honor) —
# it does not call `ensure_vector_size()` or read `embedder.dimensions`
# itself; what the store does with the bound embedder (reconcile immediately,
# or defer to its own first real connection) is entirely up to the
# implementation. `isinstance()` on a Protocol checks *every* inherited
# member (contracts.indexing.Indexer's `index`/`delete`/`clear`/`list_ids`/
# `name`, plus `bind_embedder`/`ensure_vector_size`) — a fake missing any one
# of them would silently fail the isinstance check and skip binding
# entirely, so `_FakeVectorIndexer` below implements the full Indexer
# surface, not just the two new methods. `_SlottedVectorIndexer` additionally
# proves the design needs no dynamic-attribute cooperation at all: it
# declares `__slots__` with no `_embedder` name, so any attempt by
# orchestration to `setattr` an undeclared attribute onto it would raise
# `AttributeError` — `wire()` never does that, only ever calling the public
# `bind_embedder()` method.
# ---------------------------------------------------------------------------


class _FakeEmbedderWithDimensions:
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[0.0] * self._dimensions for _ in texts]

    async def aembed(self, texts):  # type: ignore[no-untyped-def]
        return self.embed(texts)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def name(self) -> str:
        return "fake-embedder-with-dimensions"


class _FakeVectorIndexer:
    def __init__(self) -> None:
        self.bind_embedder_calls: list[object] = []
        self.ensure_vector_size_calls: list[int] = []
        self._raise: Exception | None = None

    def index(self, chunks):  # type: ignore[no-untyped-def]
        pass

    def delete(self, ids):  # type: ignore[no-untyped-def]
        pass

    def clear(self) -> None:
        pass

    def list_ids(self):  # type: ignore[no-untyped-def]
        return []

    def name(self) -> str:
        return "fake-vector-indexer"

    def bind_embedder(self, embedder: object) -> None:
        self.bind_embedder_calls.append(embedder)

    def ensure_vector_size(self, dimensions: int) -> None:
        self.ensure_vector_size_calls.append(dimensions)
        if self._raise is not None:
            raise self._raise


class _SlottedVectorIndexer:
    """A `VectorIndexer` that forbids arbitrary attributes (Codex review,
    second pass) — proves `wire()` cooperates with `bind_embedder()` alone
    and never reaches for a private attribute no Protocol member declares."""

    __slots__ = ("bound_embedder",)

    def __init__(self) -> None:
        self.bound_embedder: object | None = None

    def index(self, chunks):  # type: ignore[no-untyped-def]
        pass

    def delete(self, ids):  # type: ignore[no-untyped-def]
        pass

    def clear(self) -> None:
        pass

    def list_ids(self):  # type: ignore[no-untyped-def]
        return []

    def name(self) -> str:
        return "slotted-vector-indexer"

    def bind_embedder(self, embedder: object) -> None:
        self.bound_embedder = embedder

    def ensure_vector_size(self, dimensions: int) -> None:
        pass


def test_wire_binds_the_embedder_via_the_public_protocol_method() -> None:
    """ADR-0009 + Codex review (second pass): `wire()` must call
    `bind_embedder()`, not merely set a private attribute an implementation
    could ignore, reject via `__slots__`, or repurpose for unrelated state."""
    from modular_rag.contracts.indexing import VectorIndexer

    reg = _fake_registry()
    embedder = _FakeEmbedderWithDimensions(768)
    indexer = _FakeVectorIndexer()
    reg.register("embedder", "fake-embedder", lambda cfg: embedder)
    reg.register("indexer", "fake-indexer", lambda cfg: indexer)
    assert isinstance(indexer, VectorIndexer)  # sanity: the fake really conforms

    reg.wire(_minimal_manifest())

    assert indexer.bind_embedder_calls == [embedder]
    assert indexer.ensure_vector_size_calls == []  # not called eagerly by wire() itself


def test_wire_binds_the_embedder_on_an_implementation_with_no_dynamic_attributes() -> None:
    """The `__slots__`-based fake would raise `AttributeError` on any
    `setattr(store, "_embedder", ...)`-style injection — proves `wire()`
    only ever calls the public `bind_embedder()` method."""
    from modular_rag.contracts.indexing import VectorIndexer

    reg = _fake_registry()
    embedder = _FakeEmbedderWithDimensions(768)
    indexer = _SlottedVectorIndexer()
    reg.register("embedder", "fake-embedder", lambda cfg: embedder)
    reg.register("indexer", "fake-indexer", lambda cfg: indexer)
    assert isinstance(indexer, VectorIndexer)  # sanity: the fake really conforms

    reg.wire(_minimal_manifest())  # must not raise AttributeError

    assert indexer.bound_embedder is embedder


def test_wire_skips_embedder_binding_when_indexer_is_not_a_vector_indexer() -> None:
    """The default `_fake_registry()` indexer is a bare `object()` — must
    not crash `wire()` just because it doesn't implement `VectorIndexer`
    (e.g. a future lexical-only Indexer)."""
    reg = _fake_registry()

    container = reg.wire(_minimal_manifest())  # must not raise

    assert container.indexer is not None


def test_wire_succeeds_even_when_ensure_vector_size_would_raise() -> None:
    """ADR-0009: `ensure_vector_size()` is never called by `wire()` itself —
    an explicit `vector_size` mismatch only surfaces later, whenever the
    store itself decides to reconcile (see
    tests/unit/adapters/vectorstores/test_qdrant_store.py and
    tests/unit/app/test_preset_vector_dimensions.py for that path)."""
    reg = _fake_registry()
    embedder = _FakeEmbedderWithDimensions(768)
    indexer = _FakeVectorIndexer()
    indexer._raise = ConfigurationError(
        "vector_size=384 does not match embedder dimensions=768"
    )
    reg.register("embedder", "fake-embedder", lambda cfg: embedder)
    reg.register("indexer", "fake-indexer", lambda cfg: indexer)

    reg.wire(_minimal_manifest())  # must not raise

    assert indexer.bind_embedder_calls == [embedder]
    assert indexer.ensure_vector_size_calls == []
