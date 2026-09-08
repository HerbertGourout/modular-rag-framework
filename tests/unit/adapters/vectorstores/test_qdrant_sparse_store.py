"""Unit tests for adapters/vectorstores/qdrant_sparse_store.py — QdrantSparseStore
(Lot 5, persistent sparse retrieval). Mirrors tests/unit/adapters/vectorstores/
test_qdrant_store.py's structure and its documented scope split: `_ensure_collection()`
is a pure in-memory decision given a fake client (no live Qdrant needed) — actual
`index()`/`delete()`/`clear()`/`list_ids()`/`retrieve_by_text()` behaviour needs a
live store and is covered by tests/integration/test_qdrant_sparse_store.py instead,
matching the existing VectorRetriever/HybridRetriever/QdrantStore exclusion in
.claude/rules/tests.md.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from modular_rag.adapters.vectorstores.qdrant_sparse_store import QdrantSparseStore
from modular_rag.contracts.indexing import Indexer
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.resilience import CircuitBreaker
from modular_rag.core.sparse_vectorizer import hash_term


def test_implements_indexer_protocol():
    assert isinstance(QdrantSparseStore(), Indexer)


def test_name_returns_sparse_qdrant():
    assert QdrantSparseStore().name() == "sparse-qdrant"


def test_default_timeout_is_thirty_seconds():
    assert QdrantSparseStore()._timeout == 30.0


def test_default_avgdl_matches_fixed_size_chunkers_default_chunk_size():
    """test-specialist/architecture-reviewer review (Lot 5): the original
    128.0 default was derived from a mistaken belief that chunk_size=512
    meant ~100-130 words — FixedSizeChunker's chunk_size is token-counted
    (whitespace word count by default), so a chunk_size=512 chunk averages
    ~512 words, not ~128."""
    from modular_rag.ingestion.chunkers.fixed import FixedSizeChunker

    assert QdrantSparseStore()._avgdl == float(FixedSizeChunker().chunk_size)


@pytest.mark.parametrize("avgdl", [0.0, -1.0, -128.0])
def test_non_positive_avgdl_is_rejected_at_construction(avgdl):
    """test-specialist review (Lot 5): `avgdl` reaches here from manifest
    config (`retriever.config.avgdl` / a standalone `sparse-qdrant`
    indexer's config) unvalidated. A zero avgdl divides by zero inside
    core.sparse_vectorizer.index_sparse_vector on the first index() call —
    deep inside the method, not at construction. Same fail-fast pattern as
    DeterministicEmbedder's dimensions / DeterministicGenerator's
    max_chunks validation."""
    with pytest.raises(ConfigurationError, match=str(avgdl)):
        QdrantSparseStore(avgdl=avgdl)


def test_get_client_constructs_a_real_qdrant_client_with_the_given_timeout(monkeypatch):
    store = QdrantSparseStore(timeout=5.0)
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    client = store._get_client()

    from qdrant_client import QdrantClient

    assert isinstance(client, QdrantClient)


def test_close_releases_the_client_if_one_was_opened(monkeypatch):
    store = QdrantSparseStore()
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
    QdrantSparseStore().close()  # must not raise


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience): check_health() + the lazy-init lock.
# Mirrors tests/unit/adapters/vectorstores/test_qdrant_store.py's identical
# additions.
# ---------------------------------------------------------------------------


class _FakeHealthCollectionDescription:
    """`_FakeHealth`-prefixed, not `_FakeCollectionDescription`, to avoid
    colliding with the differently-shaped class of the same short name
    defined later in this file (for the `_ensure_collection()` tests) —
    Python silently lets the later module-level definition shadow the
    earlier one, which previously made these fakes return the wrong data
    without any import-time error (caught only by an assertion actually
    failing)."""

    def __init__(self, name):
        self.name = name


class _FakeHealthCollectionsResponse:
    def __init__(self, names):
        self.collections = [_FakeHealthCollectionDescription(n) for n in names]


class _FakeHealthSparseVectorParams:
    def __init__(self, modifier):
        self.modifier = modifier


class _FakeHealthCollectionInfo:
    """Matches the `.config.params.sparse_vectors` path `check_health()`
    and `_ensure_collection()` both read — see Codex review HIGH-001 (Lot
    6, second pass)."""

    def __init__(self, sparse_config):
        self.config = type(
            "Config", (), {"params": type("Params", (), {"sparse_vectors": sparse_config})()}
        )()


def _idf_sparse_config():
    from qdrant_client.http.models import Modifier

    return {"sparse": _FakeHealthSparseVectorParams(Modifier.IDF)}


class _FakeHealthyClient:
    """Reports the default `QdrantSparseStore()`'s collection
    (`"mrag_sparse_default"`) as existing with a correctly IDF-weighted
    sparse field — a plain `get_collections()`-only fake used to make this
    pass regardless of collection/field config, which is exactly the
    false-positive Codex review HIGH-001 (second pass) flagged."""

    def get_collections(self):
        return _FakeHealthCollectionsResponse(["mrag_sparse_default"])

    def get_collection(self, name):
        return _FakeHealthCollectionInfo(_idf_sparse_config())

    def close(self):
        pass


class _FakeUnhealthyClient:
    def get_collections(self):
        raise RuntimeError("connection refused")

    def close(self):
        pass


def test_check_health_returns_healthy_on_a_successful_get_collections_warm(monkeypatch):
    """Warm path: a client is already cached."""
    store = QdrantSparseStore()
    store._client = _FakeHealthyClient()

    results = store.check_health()

    assert len(results) == 1
    assert results[0].name == "sparse-qdrant"
    assert results[0].healthy is True


def test_check_health_reports_unhealthy_when_the_collection_does_not_exist():
    """Codex review HIGH-001 (Lot 6, second pass): see QdrantStore's
    identical test for the full rationale."""

    class _EmptyClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse([])

    store = QdrantSparseStore()
    store._client = _EmptyClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "does not exist" in results[0].detail


def test_check_health_reports_unhealthy_when_the_sparse_field_is_missing():
    """A collection created without the expected sparse field name
    previously reported healthy — the real check ran once, lazily, inside
    `_ensure_collection()`."""

    class _NoSparseFieldClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_sparse_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo({})  # no "sparse" key at all

    store = QdrantSparseStore()
    store._client = _NoSparseFieldClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "no sparse vector field" in results[0].detail


def test_check_health_reports_unhealthy_when_the_modifier_is_not_idf():
    """A sparse field present but created with the default modifier
    (`Modifier.NONE`, not IDF) silently returns TF-only scores — see
    `_ensure_collection()`'s own MED-001 (Lot 5) history for why this
    matters."""
    from qdrant_client.http.models import Modifier

    class _WrongModifierClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_sparse_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(
                {"sparse": _FakeHealthSparseVectorParams(Modifier.NONE)}
            )

    store = QdrantSparseStore()
    store._client = _WrongModifierClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "not IDF" in results[0].detail


def test_check_health_returns_unhealthy_with_a_classified_detail_warm(monkeypatch):
    """Codex review MED-002 (Lot 6): see QdrantStore's identical test."""
    store = QdrantSparseStore()
    store._client = _FakeUnhealthyClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "connection refused" not in results[0].detail
    assert results[0].detail.startswith("unreachable (")


def test_check_health_returns_healthy_on_a_successful_get_collections_cold(monkeypatch):
    """Cold path (no client ever cached): probes with a bare, throwaway
    client instead of `_get_client()` (orchestration-specialist review, Lot
    6) — see `QdrantStore`'s identical test for the full rationale."""
    import qdrant_client as qdrant_client_module

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _FakeHealthyClient())
    store = QdrantSparseStore()

    results = store.check_health()

    assert results[0].healthy is True
    assert store._client is None


def test_check_health_returns_unhealthy_with_a_classified_detail_cold(monkeypatch):
    """Codex review MED-002 (Lot 6): see QdrantStore's identical test."""
    import qdrant_client as qdrant_client_module

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _FakeUnhealthyClient())
    store = QdrantSparseStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert "connection refused" not in results[0].detail
    assert results[0].detail.startswith("unreachable (")
    assert store._client is None


class _TrackingCloseClient:
    """See `test_qdrant_store.py`'s identical fake for the full rationale
    (Codex review MEDIUM-002, Lot 6, fourth pass)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.closed = False

    def get_collections(self):
        return self._inner.get_collections()

    def get_collection(self, name):
        return self._inner.get_collection(name)

    def close(self):
        self.closed = True


def test_check_health_closes_the_cold_client_on_a_healthy_verdict(monkeypatch):
    import qdrant_client as qdrant_client_module

    tracker = _TrackingCloseClient(_FakeHealthyClient())
    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: tracker)
    store = QdrantSparseStore()

    results = store.check_health()

    assert results[0].healthy is True
    assert tracker.closed is True


def test_check_health_closes_the_cold_client_on_an_unhealthy_verdict(monkeypatch):
    import qdrant_client as qdrant_client_module

    class _MissingCollectionInner:
        def get_collections(self):
            return _FakeHealthCollectionsResponse([])

    tracker = _TrackingCloseClient(_MissingCollectionInner())
    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: tracker)
    store = QdrantSparseStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert tracker.closed is True


def test_check_health_closes_the_cold_client_when_the_probe_raises(monkeypatch):
    import qdrant_client as qdrant_client_module

    tracker = _TrackingCloseClient(_FakeUnhealthyClient())
    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: tracker)
    store = QdrantSparseStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert tracker.closed is True


def test_check_health_does_not_close_the_warm_shared_client():
    store = QdrantSparseStore()
    tracker = _TrackingCloseClient(_FakeHealthyClient())
    store._client = tracker

    results = store.check_health()

    assert results[0].healthy is True
    assert tracker.closed is False


def test_check_health_skips_the_network_call_when_the_circuit_is_open(monkeypatch):
    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    store = QdrantSparseStore(circuit_breaker=breaker)

    def _must_not_be_called():
        raise AssertionError("check_health() must not call _get_client() while circuit is open")

    monkeypatch.setattr(store, "_get_client", _must_not_be_called)

    results = store.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "circuit open"


def test_get_client_constructs_exactly_one_client_under_concurrent_calls(monkeypatch):
    import qdrant_client as qdrant_client_module

    construct_count = {"n": 0}

    class _SlowFakeClient:
        def __init__(self, **kwargs):
            construct_count["n"] += 1
            time.sleep(0.01)

        def close(self):
            pass

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", _SlowFakeClient)
    store = QdrantSparseStore()
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: store._get_client(), range(10)))

    assert construct_count["n"] == 1


def test_get_client_retries_against_a_real_unreachable_host_then_raises():
    """See `QdrantStore`'s identical test for the full rationale
    (test-specialist review, Lot 6) — the retry+circuit-breaker wrapping
    inside `_get_client()` had zero coverage through an adapter before
    this."""
    store = QdrantSparseStore(url="http://localhost:1", timeout=1.0)

    with pytest.raises(Exception):  # noqa: B017 - the real qdrant-client exception type
        store._get_client()

    assert store._client is None


def test_get_client_does_not_publish_a_client_when_ensure_collection_fails(monkeypatch):
    """Same publish-after-validate discipline as QdrantStore (Codex review,
    second pass, HIGH-002 on that store) — a caller that catches the
    ConfigurationError and retries must not find a stale, unvalidated client."""
    store = QdrantSparseStore()
    monkeypatch.setattr(
        store,
        "_ensure_collection",
        lambda: (_ for _ in ()).throw(ConfigurationError("missing sparse field")),
    )

    with pytest.raises(ConfigurationError):
        store._get_client()


def test_get_client_closes_the_rejected_client_when_ensure_collection_fails(monkeypatch):
    """Codex review (Lot 5, MED-001): the rejected client's own HTTP
    transport was previously never closed here — just discarded by
    clearing `self._client` — leaking one open connection per failed/
    retried wiring attempt. The new strict Modifier.IDF validation
    (Codex review, MED-001 on a prior round) makes this path realistically
    reachable during a misconfigured migration, not just a hypothetical."""
    import qdrant_client as qdrant_client_module

    closed = []

    class _FakeClient:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kwargs: _FakeClient())
    store = QdrantSparseStore()
    monkeypatch.setattr(
        store,
        "_ensure_collection",
        lambda: (_ for _ in ()).throw(ConfigurationError("missing sparse field")),
    )

    with pytest.raises(ConfigurationError):
        store._get_client()

    assert closed == [True]

    assert store._client is None


# ---------------------------------------------------------------------------
# _ensure_collection(): the network-touching half of the guarantee.
# ---------------------------------------------------------------------------


class _FakeCollectionsList:
    def __init__(self, names: list[str]) -> None:
        self.collections = [_FakeCollectionDescription(n) for n in names]


class _FakeCollectionDescription:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSparseFieldParams:
    def __init__(self, modifier: object) -> None:
        self.modifier = modifier


class _FakeSparseVectorsParams:
    def __init__(self, modifier: object | None) -> None:
        # `modifier=None` means "no sparse field at all" — anything else
        # (including a real Modifier.NONE) means "field exists, with this
        # modifier value" (Codex review, Lot 5, MED-001 — the field-presence
        # and modifier-value checks are now two independent tests).
        self.sparse_vectors = (
            {"sparse": _FakeSparseFieldParams(modifier)} if modifier is not None else {}
        )


class _FakeCollectionConfig:
    def __init__(self, modifier: object | None) -> None:
        self.params = _FakeSparseVectorsParams(modifier)


class _FakeCollectionInfo:
    def __init__(self, modifier: object | None) -> None:
        self.config = _FakeCollectionConfig(modifier)


class _FakeQdrantClient:
    def __init__(self, existing_collections: dict[str, object | None]) -> None:
        self._existing = existing_collections
        self.created: list[tuple[str, list[str]]] = []

    def get_collections(self) -> _FakeCollectionsList:
        return _FakeCollectionsList(list(self._existing))

    def get_collection(self, name: str) -> _FakeCollectionInfo:
        return _FakeCollectionInfo(self._existing[name])

    def create_collection(self, collection_name, vectors_config, sparse_vectors_config):  # type: ignore[no-untyped-def]
        assert vectors_config is None  # sparse-only: no dense field created
        self.created.append((collection_name, list(sparse_vectors_config.keys())))


def test_ensure_collection_creates_a_new_sparse_only_collection():
    store = QdrantSparseStore(collection="docs_sparse")
    fake_client = _FakeQdrantClient(existing_collections={})
    store._client = fake_client

    store._ensure_collection()

    assert fake_client.created == [("docs_sparse", ["sparse"])]


def test_ensure_collection_does_nothing_when_an_existing_collection_has_the_sparse_field_with_idf():
    from qdrant_client.http.models import Modifier

    store = QdrantSparseStore(collection="docs_sparse")
    fake_client = _FakeQdrantClient(existing_collections={"docs_sparse": Modifier.IDF})
    store._client = fake_client

    store._ensure_collection()  # must not raise

    assert fake_client.created == []


def test_ensure_collection_raises_when_an_existing_collection_lacks_the_sparse_field():
    """A collection that predates this store, or was created by something
    else, without the expected sparse vector field name — must be rejected
    here, before any upsert, not surfaced as an opaque KeyError deep inside
    index()/retrieve_by_text()."""
    store = QdrantSparseStore(collection="docs_sparse")
    fake_client = _FakeQdrantClient(existing_collections={"docs_sparse": None})
    store._client = fake_client

    with pytest.raises(ConfigurationError, match="sparse vector field"):
        store._ensure_collection()


def test_ensure_collection_raises_when_the_sparse_field_exists_but_lacks_the_idf_modifier():
    """Codex review (Lot 5, MED-001): the field-name check alone is
    insufficient — a collection whose sparse field is named "sparse" but
    was created with the default modifier (Modifier.NONE, not IDF) passed
    validation before this fix, silently returning TF-only scores instead
    of the BM25-like ranking this store promises (index_sparse_vector()
    deliberately omits IDF, relying on Qdrant's Modifier.IDF to supply it
    server-side)."""
    from qdrant_client.http.models import Modifier

    store = QdrantSparseStore(collection="docs_sparse")
    fake_client = _FakeQdrantClient(existing_collections={"docs_sparse": Modifier.NONE})
    store._client = fake_client

    with pytest.raises(ConfigurationError, match="Modifier.IDF"):
        store._ensure_collection()

    assert fake_client.created == []


# ---------------------------------------------------------------------------
# index(): pure sparse-vector-computation logic, unit-testable via a fake
# client that captures the upserted points — no live Qdrant needed. Closes
# a test-specialist-flagged gap (Lot 5): `self._avgdl`/`_k1`/`_b` forwarding
# into core.sparse_vectorizer.index_sparse_vector previously had zero
# coverage anywhere (the only exerciser was tests/integration/, which is
# never executed in this environment) — a transposed kwarg
# (e.g. `k1=self._b`) would have been invisible to the whole suite.
# ---------------------------------------------------------------------------


class _FakeUpsertClient:
    def __init__(self) -> None:
        self.upserted_points: list = []

    def upsert(self, collection_name: str, points: list) -> None:  # type: ignore[no-untyped-def]
        self.upserted_points.extend(points)


def test_index_computes_sparse_vectors_using_the_configured_avgdl_k1_b(monkeypatch):
    store = QdrantSparseStore(avgdl=1.0, k1=1.2, b=0.75)
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(id=new_id(), doc_id="doc-1", content="a")  # dl=1 == avgdl

    n = store.index([chunk])

    assert n == 1
    point = fake_client.upserted_points[0]
    sparse_vector = point.vector["sparse"]
    a_index = hash_term("a")
    assert sparse_vector.indices == [a_index]
    # Golden value at dl == avgdl (same derivation as
    # tests/unit/core/test_sparse_vectorizer.py's k1-pinning test):
    # tf*(k1+1)/(tf+k1) = 1*2.2/2.2 == 1.0.
    assert sparse_vector.values[0] == pytest.approx(1.0)


def test_index_forwards_a_non_default_avgdl_k1_b_and_changes_the_result(monkeypatch):
    """Differential proof that _avgdl/_k1/_b actually reach
    index_sparse_vector, rather than a hardcoded/default value being used
    regardless of construction args — construct two stores with different
    tuning and confirm they compute different weights for the same chunk."""
    default_client = _FakeUpsertClient()
    default_store = QdrantSparseStore(avgdl=2.0)
    monkeypatch.setattr(default_store, "_get_client", lambda: default_client)

    tuned_client = _FakeUpsertClient()
    tuned_store = QdrantSparseStore(avgdl=2.0, k1=3.0, b=0.1)
    monkeypatch.setattr(tuned_store, "_get_client", lambda: tuned_client)

    chunk = Chunk(id=new_id(), doc_id="doc-1", content="a a")

    default_store.index([chunk])
    tuned_store.index([chunk])

    a_index = hash_term("a")
    default_weight = default_client.upserted_points[0].vector["sparse"].values[
        default_client.upserted_points[0].vector["sparse"].indices.index(a_index)
    ]
    tuned_weight = tuned_client.upserted_points[0].vector["sparse"].values[
        tuned_client.upserted_points[0].vector["sparse"].indices.index(a_index)
    ]
    assert default_weight != tuned_weight


def test_index_skips_a_chunk_with_no_word_tokens(monkeypatch):
    store = QdrantSparseStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(id=new_id(), doc_id="doc-1", content="!!! ??? ...")

    n = store.index([chunk])

    assert n == 0
    assert fake_client.upserted_points == []


# ---------------------------------------------------------------------------
# Codex review (Lot 5, HIGH-001): `Chunk.metadata` accepts arbitrary keys
# unvalidated, including ones that collide with the store's own structured
# payload fields. A chunk indexed *after* TenantIsolationPolicy.
# enforce_ingest() validated `chunk.tenant_id` could still carry
# metadata={"tenant_id": "<other tenant>"} — if the payload dict spreads
# metadata *after* the structured fields, that spoofed value silently wins,
# and retrieve_by_text()'s server-side tenant filter then enforces the
# falsified value, not the real one. Reproduced and confirmed against the
# pre-fix code before writing this test.
# ---------------------------------------------------------------------------


def test_index_does_not_let_metadata_override_the_real_tenant_id(monkeypatch):
    store = QdrantSparseStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        tenant_id="tenant-a",
        metadata={"tenant_id": "tenant-b"},
    )

    store.index([chunk])

    payload = fake_client.upserted_points[0].payload
    assert payload["tenant_id"] == "tenant-a"


@pytest.mark.parametrize(
    ("field", "real_value"),
    [
        ("doc_id", "doc-1"),
        ("content", "hello world"),
        ("modality", "text"),
        ("start_char", 0),
        ("end_char", 11),
        ("page", None),
    ],
)
def test_index_does_not_let_metadata_override_any_structured_payload_field(
    monkeypatch, field, real_value
):
    store = QdrantSparseStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        start_char=0,
        end_char=11,
        tenant_id="tenant-a",
        metadata={field: "spoofed-value"},
    )

    store.index([chunk])

    payload = fake_client.upserted_points[0].payload
    assert payload[field] == real_value


# ---------------------------------------------------------------------------
# Lot 20 (Codex review pass 1, HIGH-003): classification round-trip. Same bug
# shape as tenant_id above -- previously dropped from the payload in index()
# and never reconstructed in retrieve_by_text(), which silently defeated
# governance.egress_policy for the real Qdrant sparse path.
# ---------------------------------------------------------------------------


def test_index_persists_classification_in_the_payload(monkeypatch):
    from modular_rag.core.enums import DataClassification

    store = QdrantSparseStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        classification=DataClassification.RESTRICTED,
    )

    store.index([chunk])

    assert fake_client.upserted_points[0].payload["classification"] == "restricted"


def test_retrieve_by_text_reconstructs_classification_from_the_payload(monkeypatch):
    class _ClassifiedHitClient:
        def query_points(self, **kwargs):  # type: ignore[no-untyped-def]
            class _Hit:
                id = "chunk-1"
                score = 0.9
                payload = {
                    "doc_id": "doc-1",
                    "content": "restricted content",
                    "start_char": 0,
                    "end_char": 19,
                    "classification": "restricted",
                }

            class _Result:
                points = [_Hit()]

            return _Result()

    store = QdrantSparseStore()
    monkeypatch.setattr(store, "_get_client", lambda: _ClassifiedHitClient())

    results = store.retrieve_by_text("restricted content", k=5)

    assert len(results) == 1
    assert results[0].chunk.classification == "restricted"
    assert "classification" not in results[0].chunk.metadata


def test_index_still_preserves_legitimate_non_colliding_metadata(monkeypatch):
    """The fix must not drop legitimate metadata entirely — only structured
    fields are protected from being overridden."""
    store = QdrantSparseStore()
    fake_client = _FakeUpsertClient()
    monkeypatch.setattr(store, "_get_client", lambda: fake_client)
    chunk = Chunk(
        id=new_id(),
        doc_id="doc-1",
        content="hello world",
        tenant_id="tenant-a",
        metadata={"source": "manual-upload.txt"},
    )

    store.index([chunk])

    payload = fake_client.upserted_points[0].payload
    assert payload["source"] == "manual-upload.txt"
    assert payload["tenant_id"] == "tenant-a"
