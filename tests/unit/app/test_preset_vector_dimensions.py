"""Proves the real, current manifests/presets/*.yaml files wire to a
QdrantStore with the *correct* vector dimension for their configured
embedder — this correction's explicit acceptance criterion ("ajouter un test
prouvant que les presets peuvent réellement indexer").

Before this correction (see ADR-0009,
docs/adr/0009-vector-indexer-dimension-reconciliation.md), `secure-enterprise-rag.yaml`
and `langgraph-rag.yaml` both select `BAAI/bge-base-en-v1.5` (768-dim) without
ever setting `indexer.config.vector_size`, so `QdrantStore`'s old
`int = 384` default would have created a 384-dim collection — indexing real
768-dim vectors into it would fail. `local-hybrid-rag.yaml`'s
`bge-small-en-v1.5` already matches 384 by coincidence, which is exactly why
this class of bug went unnoticed.

Per ADR-0009, `ComponentRegistry.wire()` calls `QdrantStore.bind_embedder()`
— a real `VectorIndexer` protocol method — instead of reading
`embedder.dimensions` itself; reconciliation happens lazily inside
`QdrantStore._get_client()`, the first time a live connection is actually
needed. Two things would otherwise touch the network here: `_ensure_collection()`
is monkeypatched to a no-op, matching the existing convention in
tests/unit/adapters/vectorstores/test_qdrant_store.py, and — per Codex review
(second pass, MED-002) — the lazily-imported `qdrant_client.QdrantClient`
itself is replaced with a network-free fake, since its real constructor
attempts a server-version compatibility request even before
`_ensure_collection()` runs. This keeps the test genuinely network-free while
still exercising the real HuggingFaceEmbedder, real QdrantStore, and real
ComponentRegistry.wire() together. `load_manifest()` (raw load, no
`${VAR}`/`secret://` interpolation) is used instead of `resolve_manifest()`
so `secure-enterprise-rag.yaml`'s environment-variable requirements don't
need to be satisfied just to check wiring.
"""
from __future__ import annotations

import pytest

from modular_rag.app.bootstrap import load_manifest
from modular_rag.app.default_factories import create_default_registry
from modular_rag.core.errors import ConfigurationError


class _FakeQdrantClient:
    """Stands in for `qdrant_client.QdrantClient` so `_get_client()` never
    opens a real connection — its own constructor, not just
    `_ensure_collection()`, is what makes a network attempt (Codex review,
    second pass)."""

    def __init__(self, url: str, api_key: str | None, timeout: int) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout


def _wired_vector_size(preset_path: str, monkeypatch: pytest.MonkeyPatch) -> int:
    manifest = load_manifest(preset_path)
    registry = create_default_registry()
    container = registry.wire(manifest)
    assert container.indexer is not None
    monkeypatch.setattr("qdrant_client.QdrantClient", _FakeQdrantClient)
    monkeypatch.setattr(container.indexer, "_ensure_collection", lambda: None)

    container.indexer._get_client()  # triggers lazy dimension reconciliation

    assert isinstance(container.indexer._client, _FakeQdrantClient)  # never a real client
    return container.indexer.vector_size  # type: ignore[no-any-return]


def test_local_hybrid_rag_wires_a_384_dimensional_collection(monkeypatch) -> None:
    assert _wired_vector_size("manifests/presets/local-hybrid-rag.yaml", monkeypatch) == 384


def test_secure_enterprise_rag_wires_a_768_dimensional_collection(monkeypatch) -> None:
    """Before this lot: silently defaulted to 384 despite bge-base-en-v1.5's
    real 768-dimensional output."""
    assert _wired_vector_size("manifests/presets/secure-enterprise-rag.yaml", monkeypatch) == 768


def test_langgraph_rag_wires_a_768_dimensional_collection(monkeypatch) -> None:
    """Same bug as secure-enterprise-rag.yaml, same fix."""
    assert _wired_vector_size("manifests/presets/langgraph-rag.yaml", monkeypatch) == 768


def test_an_explicitly_incompatible_vector_size_is_rejected_before_indexing(monkeypatch) -> None:
    """The full real pipeline — real HuggingFaceEmbedder, real QdrantStore, real
    ComponentRegistry.wire() — for the "configuration incompatible rejetée avant
    indexation" acceptance criterion. Prior coverage exercised this path only
    through fakes (test_registry.py) or QdrantStore.ensure_vector_size() in
    isolation (test_indexer_conformance.py); this proves the real components
    actually wire that way together (test-specialist review).

    Per ADR-0009, the rejection now happens at the first real store operation
    (here, `_get_client()`) rather than at `wire()` itself — still strictly
    before any client is constructed or `_ensure_collection()` would create
    or touch anything, so this test doesn't even need the `QdrantClient` fake
    the success-path tests above use."""
    manifest = load_manifest("manifests/presets/local-hybrid-rag.yaml")
    assert manifest.indexer is not None
    manifest.indexer.config["vector_size"] = 1024  # bge-small-en-v1.5 is 384-dim

    registry = create_default_registry()
    container = registry.wire(manifest)  # succeeds: only binds the embedder now
    assert container.indexer is not None
    monkeypatch.setattr(container.indexer, "_ensure_collection", lambda: None)

    with pytest.raises(ConfigurationError):
        container.indexer._get_client()

    assert container.indexer._client is None  # never got as far as a client


def test_local_hybrid_and_langgraph_presets_no_longer_share_a_collection_name() -> None:
    """The collection-name collision this lot's investigation found: both
    presets pointed at `documents` on the same default localhost:6333, at
    two different dimensions — a live deployment running both would have
    hit ConfigurationError (this lot's own new check) or, before this lot,
    silently mixed 384- and 768-dim vectors in one collection."""
    local = load_manifest("manifests/presets/local-hybrid-rag.yaml")
    langgraph = load_manifest("manifests/presets/langgraph-rag.yaml")

    assert local.indexer is not None
    assert langgraph.indexer is not None
    assert local.indexer.config["collection"] != langgraph.indexer.config["collection"]
