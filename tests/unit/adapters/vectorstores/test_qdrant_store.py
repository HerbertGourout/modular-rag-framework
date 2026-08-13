"""Unit tests for adapters/vectorstores/qdrant_store.py — QdrantStore. No
prior direct unit coverage existed (only integration, requiring a live
Qdrant). Scoped to Lot 14 (docs/refactoring-plan.md — "timeouts", "own and
close clients/resources"): `_ensure_collection()` needs a live server, so
it's monkeypatched to a no-op here — this proves client construction
accepts the `timeout` kwarg without needing Qdrant itself running.

Vector-dimension tests (ADR-0009,
docs/adr/0009-vector-indexer-dimension-reconciliation.md) below use
hand-built fake client/collection-info objects rather than real
qdrant_client Pydantic models — `CollectionInfo` requires several unrelated
mandatory fields (status, optimizer_status, segments_count, payload_schema)
just to reach `.config.params.vectors.size`, which these tests never touch
beyond that one attribute path, verified for real via
`qdrant_client.http.models` before writing these fakes.
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.contracts.indexing import VectorIndexer
from modular_rag.core.errors import ConfigurationError


def test_default_timeout_is_thirty_seconds():
    assert QdrantStore()._timeout == 30.0


def test_get_client_constructs_a_real_qdrant_client_with_the_given_timeout(monkeypatch):
    store = QdrantStore(timeout=5.0)
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    client = store._get_client()

    from qdrant_client import QdrantClient

    assert isinstance(client, QdrantClient)


def test_close_releases_the_client_if_one_was_opened(monkeypatch):
    store = QdrantStore()
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)
    store._get_client()
    assert store._client is not None

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake = _FakeClient()
    store._client = fake

    store.close()

    assert fake.closed is True
    assert store._client is None


def test_close_is_a_no_op_when_no_client_was_ever_opened():
    QdrantStore().close()  # must not raise


# ---------------------------------------------------------------------------
# ADR-0009 — embedder/Qdrant vector-dimension consistency. Acceptance
# criteria: no silent default to 384, derive when absent, verify when
# explicit, raise ConfigurationError before collection creation/use on any
# mismatch.
# ---------------------------------------------------------------------------


def test_implements_vector_indexer_protocol():
    assert isinstance(QdrantStore(), VectorIndexer)


def test_vector_size_defaults_to_384_when_not_given():
    assert QdrantStore().vector_size == 384


def test_vector_size_reflects_an_explicit_constructor_value():
    assert QdrantStore(vector_size=768).vector_size == 768


def test_ensure_vector_size_adopts_the_given_dimension_when_not_explicit():
    """The store was constructed with no vector_size (local/unsecured
    manifest default) — deriving from the wired embedder replaces the
    384 fallback, closing the "no silent default" acceptance criterion."""
    store = QdrantStore()

    store.ensure_vector_size(768)

    assert store.vector_size == 768


def test_ensure_vector_size_accepts_a_matching_explicit_value():
    store = QdrantStore(vector_size=768)

    store.ensure_vector_size(768)  # must not raise

    assert store.vector_size == 768


def test_ensure_vector_size_raises_on_an_explicit_mismatch():
    store = QdrantStore(vector_size=384)

    with pytest.raises(ConfigurationError, match="384"):
        store.ensure_vector_size(768)


def test_ensure_vector_size_error_message_names_both_dimensions():
    store = QdrantStore(vector_size=384)

    with pytest.raises(ConfigurationError) as exc_info:
        store.ensure_vector_size(768)

    assert "384" in str(exc_info.value)
    assert "768" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ADR-0009: `_get_client()` reconciles a bound embedder (via the public
# `bind_embedder()` VectorIndexer protocol method — Codex review, second
# pass: not a private-attribute injection convention — see
# ComponentRegistry.wire()) the first time a live connection is actually
# needed, rather than `wire()` calling `ensure_vector_size()` eagerly. This
# keeps a custom embedder whose `.dimensions` requires a real model load from
# being forced to do so merely because a manifest was wired.
# ---------------------------------------------------------------------------


class _FakeEmbedder:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions


def test_bind_embedder_does_not_itself_call_ensure_vector_size(monkeypatch):
    store = QdrantStore()

    store.bind_embedder(_FakeEmbedder(768))

    assert store.vector_size == 384  # unreconciled until _get_client() runs


def test_get_client_reconciles_vector_size_from_a_bound_embedder(monkeypatch):
    store = QdrantStore()
    store.bind_embedder(_FakeEmbedder(768))
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    store._get_client()

    assert store.vector_size == 768


def test_get_client_does_not_touch_dimensions_when_no_embedder_was_bound(monkeypatch):
    """No embedder bound (e.g. constructed directly, outside
    `ComponentRegistry.wire()`) — `_get_client()` must not touch anything
    embedder-related, preserving the pre-existing 384 fallback for callers
    that never opt into dimension reconciliation."""
    store = QdrantStore()
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    store._get_client()

    assert store.vector_size == 384


def test_get_client_raises_before_constructing_a_client_on_a_bound_mismatch(monkeypatch):
    store = QdrantStore(vector_size=384)
    store.bind_embedder(_FakeEmbedder(768))
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    with pytest.raises(ConfigurationError, match="768"):
        store._get_client()

    assert store._client is None  # never got as far as constructing a client


def test_get_client_does_not_publish_a_client_when_ensure_collection_fails(monkeypatch):
    """Codex review (second pass, HIGH-002): `self._client` was previously
    assigned *before* `_ensure_collection()` ran, so a caller that caught
    the resulting `ConfigurationError` and retried would find `self._client`
    already non-None on the next call — `_get_client()` would then skip
    `_ensure_collection()` entirely (it only runs inside
    `if self._client is None:`) and hand back the never-actually-validated
    client."""
    store = QdrantStore()
    monkeypatch.setattr(
        store,
        "_ensure_collection",
        lambda: (_ for _ in ()).throw(ConfigurationError("dimension mismatch")),
    )

    with pytest.raises(ConfigurationError):
        store._get_client()

    assert store._client is None


def test_get_client_closes_the_rejected_client_when_ensure_collection_fails(monkeypatch):
    """Codex review (Lot 5, MED-001): the rejected client's own HTTP
    transport was previously never closed here — just discarded by
    clearing `self._client` — leaking one open connection per failed/
    retried wiring attempt (e.g. against a still-incompatible collection
    during a migration)."""
    import qdrant_client as qdrant_client_module

    closed = []

    class _FakeClient:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kwargs: _FakeClient())
    store = QdrantStore()
    monkeypatch.setattr(
        store,
        "_ensure_collection",
        lambda: (_ for _ in ()).throw(ConfigurationError("dimension mismatch")),
    )

    with pytest.raises(ConfigurationError):
        store._get_client()

    assert closed == [True]


def test_get_client_re_validates_on_retry_after_ensure_collection_failed(monkeypatch):
    """The regression this closes: a second `_get_client()` call after a
    first failed one must re-run `_ensure_collection()` — not silently
    return a client that was never actually validated."""
    store = QdrantStore()
    calls: list[None] = []

    def _flaky_ensure_collection() -> None:
        calls.append(None)
        if len(calls) == 1:
            raise ConfigurationError("dimension mismatch")

    monkeypatch.setattr(store, "_ensure_collection", _flaky_ensure_collection)

    with pytest.raises(ConfigurationError):
        store._get_client()

    client = store._get_client()  # retry: must re-validate, not bypass

    assert len(calls) == 2  # _ensure_collection() actually ran again
    assert client is store._client


# ---------------------------------------------------------------------------
# _ensure_collection(): the network-touching half of the guarantee. A fresh
# collection is created at `vector_size`; an *existing* collection with a
# different dimension must be caught here — deriving/checking at wire() time
# only protects the very first creation (QdrantStore never recreates an
# existing collection), so this is where a stale collection is actually
# caught, before any upsert.
# ---------------------------------------------------------------------------


class _FakeCollectionsList:
    def __init__(self, names: list[str]) -> None:
        self.collections = [_FakeCollectionDescription(n) for n in names]


class _FakeCollectionDescription:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeVectorParams:
    def __init__(self, size: int) -> None:
        self.size = size


class _FakeCollectionParams:
    def __init__(self, size: int) -> None:
        self.vectors = _FakeVectorParams(size)


class _FakeCollectionConfig:
    def __init__(self, size: int) -> None:
        self.params = _FakeCollectionParams(size)


class _FakeCollectionInfo:
    def __init__(self, size: int) -> None:
        self.config = _FakeCollectionConfig(size)


class _FakeQdrantClient:
    def __init__(self, existing_collections: dict[str, int]) -> None:
        self._existing = existing_collections
        self.created: list[tuple[str, int]] = []

    def get_collections(self) -> _FakeCollectionsList:
        return _FakeCollectionsList(list(self._existing))

    def get_collection(self, name: str) -> _FakeCollectionInfo:
        return _FakeCollectionInfo(self._existing[name])

    def create_collection(self, collection_name: str, vectors_config) -> None:  # type: ignore[no-untyped-def]
        self.created.append((collection_name, vectors_config.size))


def test_ensure_collection_creates_a_new_collection_at_the_configured_size():
    store = QdrantStore(collection="docs", vector_size=768)
    fake_client = _FakeQdrantClient(existing_collections={})
    store._client = fake_client

    store._ensure_collection()

    assert fake_client.created == [("docs", 768)]


def test_ensure_collection_does_nothing_when_an_existing_collection_matches():
    store = QdrantStore(collection="docs", vector_size=384)
    fake_client = _FakeQdrantClient(existing_collections={"docs": 384})
    store._client = fake_client

    store._ensure_collection()  # must not raise

    assert fake_client.created == []


def test_ensure_collection_raises_when_an_existing_collection_has_a_different_dimension():
    """The critical fail-closed case retrieval-specialist review flagged:
    deriving/checking vector_size at wire() time only guards the very first
    collection creation. A collection created earlier (e.g. by a different
    embedder/manifest) with a different dimension must still be caught here,
    before any upsert — not surfaced as an opaque Qdrant-side rejection."""
    store = QdrantStore(collection="docs", vector_size=768)
    fake_client = _FakeQdrantClient(existing_collections={"docs": 384})
    store._client = fake_client

    with pytest.raises(ConfigurationError, match="384"):
        store._ensure_collection()

    assert fake_client.created == []  # never attempted to (re)create


class _FakeNamedVectorsParams:
    """Shaped like a real qdrant_client CollectionParams whose `vectors` is a
    `dict[str, VectorParams]` (named vectors) rather than a single unnamed
    `VectorParams` — has no `.size` of its own."""

    def __init__(self, names: list[str]) -> None:
        self.vectors = {name: _FakeVectorParams(128) for name in names}


class _FakeNamedVectorsCollectionInfo:
    def __init__(self, names: list[str]) -> None:
        self.config = _FakeCollectionConfig.__new__(_FakeCollectionConfig)
        self.config.params = _FakeNamedVectorsParams(names)


def test_ensure_collection_raises_a_configuration_error_for_named_vector_collections():
    """test-specialist review: `info.config.params.vectors` is a dict for
    a named-vector collection, which has no `.size` — before this guard, that
    surfaced as an opaque AttributeError instead of the fail-closed
    ConfigurationError the rest of this contract promises. QdrantStore itself
    never creates named-vector collections (see `_ensure_collection`'s
    `create_collection` call above — no `vector_name` given), so this only
    fires against a pre-existing collection created by something else."""
    store = QdrantStore(collection="docs", vector_size=768)
    fake_client = _FakeQdrantClient(existing_collections={"docs": 768})
    fake_client.get_collection = lambda name: _FakeNamedVectorsCollectionInfo(["text", "image"])  # type: ignore[method-assign]
    store._client = fake_client

    with pytest.raises(ConfigurationError, match="named vector"):
        store._ensure_collection()


# ---------------------------------------------------------------------------
# Codex review (Lot 5, HIGH-001): `Chunk.metadata` accepts arbitrary keys
# unvalidated, including ones that collide with the store's own structured
# payload fields (doc_id, tenant_id, etc.). Pre-existing bug in this store
# (predates Lot 5, found while writing the equivalent test for the new
# QdrantSparseStore) — `**chunk.metadata` was spread *after* the structured
# fields in `index()`'s payload dict, so a chunk indexed after
# TenantIsolationPolicy.enforce_ingest() validated `chunk.tenant_id` could
# still carry metadata={"tenant_id": "<other tenant>"} and have that spoofed
# value silently win.
# ---------------------------------------------------------------------------


class _FakeUpsertClient:
    def __init__(self) -> None:
        self.upserted_points: list = []

    def upsert(self, collection_name: str, points: list) -> None:  # type: ignore[no-untyped-def]
        self.upserted_points.extend(points)


def test_index_does_not_let_metadata_override_the_real_tenant_id(monkeypatch):
    from modular_rag.core.ids import new_id
    from modular_rag.core.models.chunk import Chunk

    store = QdrantStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        tenant_id="tenant-a",
        metadata={"tenant_id": "tenant-b"},
    )
    chunk.embedding = [0.1, 0.2]

    store.index([chunk])

    payload = fake_client.upserted_points[0].payload
    assert payload["tenant_id"] == "tenant-a"


def test_index_still_preserves_legitimate_non_colliding_metadata(monkeypatch):
    from modular_rag.core.ids import new_id
    from modular_rag.core.models.chunk import Chunk

    store = QdrantStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        tenant_id="tenant-a",
        metadata={"source": "manual-upload.txt"},
    )
    chunk.embedding = [0.1, 0.2]

    store.index([chunk])

    payload = fake_client.upserted_points[0].payload
    assert payload["source"] == "manual-upload.txt"
    assert payload["tenant_id"] == "tenant-a"
