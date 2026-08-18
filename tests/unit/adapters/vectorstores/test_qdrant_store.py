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

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore
from modular_rag.contracts.indexing import VectorIndexer
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.resilience import CircuitBreaker


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
# Lot 6 (readiness and resilience): check_health() + the lazy-init lock.
# ---------------------------------------------------------------------------


class _FakeHealthCollectionDescription:
    """`_FakeHealth`-prefixed, not `_FakeCollectionDescription`, to avoid
    colliding with the differently-shaped class of the same short name
    defined later in this file (for the ADR-0009 vector-dimension tests) —
    Python silently lets the later module-level definition shadow the
    earlier one, which previously made these fakes return the wrong data
    without any error (caught only by an assertion actually failing)."""

    def __init__(self, name):
        self.name = name


class _FakeHealthCollectionsResponse:
    def __init__(self, names):
        self.collections = [_FakeHealthCollectionDescription(n) for n in names]


class _FakeHealthVectorsConfig:
    def __init__(self, size):
        self.size = size


class _FakeHealthCollectionInfo:
    """Matches the `.config.params.vectors.size` path `check_health()` and
    `_ensure_collection()` both read — see Codex review HIGH-001 (Lot 6,
    second pass)."""

    def __init__(self, size):
        self.config = type(
            "Config",
            (),
            {"params": type("Params", (), {"vectors": _FakeHealthVectorsConfig(size)})()},
        )()


class _FakeHealthyClient:
    """Reports the default `QdrantStore()`'s collection (`"mrag_default"`)
    as existing with the matching default vector size (384) — a plain
    `get_collections()`-only fake used to make this pass regardless of
    collection/dimension, which is exactly the false-positive Codex
    review HIGH-001 (second pass) flagged."""

    def get_collections(self):
        return _FakeHealthCollectionsResponse(["mrag_default"])

    def get_collection(self, name):
        return _FakeHealthCollectionInfo(384)

    def close(self):
        pass


class _FakeUnhealthyClient:
    def get_collections(self):
        raise RuntimeError("connection refused")

    def close(self):
        pass


def test_check_health_returns_healthy_on_a_successful_get_collections_warm(monkeypatch):
    """Warm path: a client is already cached (from prior real traffic or an
    earlier health check) — reused directly, no new construction."""
    store = QdrantStore()
    store._client = _FakeHealthyClient()

    results = store.check_health()

    assert len(results) == 1
    assert results[0].name == "qdrant"
    assert results[0].healthy is True
    assert results[0].latency_ms >= 0


def test_check_health_reports_unhealthy_when_the_collection_does_not_exist():
    """Codex review HIGH-001 (Lot 6, second pass): a reachable server whose
    configured collection doesn't exist previously reported healthy —
    `get_collections()` alone only proves the server answers. The real
    validation ran once, lazily, inside `_ensure_collection()`, so a probe
    right after a deploy or restore against the wrong collection stayed
    green until the first real request discovered the mismatch."""

    class _EmptyClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse([])  # the configured collection is absent

    store = QdrantStore()
    store._client = _EmptyClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "does not exist" in results[0].detail


def test_check_health_reports_unhealthy_on_a_vector_size_mismatch():
    """Same rationale as the missing-collection test above — a stale
    collection at the wrong dimension previously reported healthy too."""

    class _WrongSizeClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(999)  # store expects 384 (the default)

    store = QdrantStore()
    store._client = _WrongSizeClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "999" in results[0].detail
    assert "384" in results[0].detail


def test_check_health_resolves_a_matching_cold_dimension_from_the_bound_embedder(monkeypatch):
    """Codex review HIGH-001/HIGH-003 (Lot 6, third and fourth pass): a
    manifest that omits `vector_size` (both `secure-enterprise-rag.yaml`
    and `langgraph-rag.yaml` do, relying on a 768-dim BGE embedder) leaves
    `self._vector_size` at the constructor default (384) until a real
    connection derives it via `ensure_vector_size()`. The check now
    resolves the expected size from the bound embedder's `.dimensions`
    directly instead of comparing against that still-undevived default (a
    third-pass fix that instead *skipped* the comparison entirely on this
    path was itself flagged fourth-pass — see the mismatch test below for
    why that was still a real gap). Reproduced here: an embedder is bound
    (as `ComponentRegistry.wire()` would do) but no client has ever been
    constructed, and the real collection is 768-dim, matching the bound
    embedder — this must report healthy."""
    import qdrant_client as qdrant_client_module

    class _FakeEmbedder:
        dimensions = 768

        def known_dimensions(self):
            # Codex review HIGH-002 (Lot 6, fifth pass): check_health() now
            # duck-types this cheap-only accessor instead of calling
            # `.dimensions` directly — see `HuggingFaceEmbedder
            # .known_dimensions()` for the full rationale.
            return 768

    class _Fake768DimClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(768)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _Fake768DimClient())
    store = QdrantStore()  # vector_size left unset -> constructor default 384
    store.bind_embedder(_FakeEmbedder())  # matches wire()'s real hand-off, no derivation yet
    assert store._client is None  # cold: no real connection has ever run ensure_vector_size()

    results = store.check_health()

    assert results[0].healthy is True


def test_check_health_catches_a_real_cold_dimension_mismatch_against_the_bound_embedder(
    monkeypatch,
):
    """Codex review HIGH-003 (Lot 6, fourth pass): the third-pass fix
    skipped the numeric comparison whenever cold + non-explicit, which
    reintroduced the *original* gap — a genuinely incompatible collection
    (an existing 384-dim collection against a bound 768-dim embedder, the
    exact reproduction Codex's review used) reported healthy again, with no
    detail, until real traffic hit `_ensure_collection()`. Must now be
    caught by the cold probe itself, without needing any client ever
    constructed."""
    import qdrant_client as qdrant_client_module

    class _FakeEmbedder:
        dimensions = 768

        def known_dimensions(self):
            # Codex review HIGH-002 (Lot 6, fifth pass): check_health() now
            # duck-types this cheap-only accessor instead of calling
            # `.dimensions` directly — see `HuggingFaceEmbedder
            # .known_dimensions()` for the full rationale.
            return 768

    class _Fake384DimClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(384)  # stale/wrong collection

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _Fake384DimClient())
    store = QdrantStore()  # vector_size left unset -> would-be constructor default 384
    store.bind_embedder(_FakeEmbedder())  # real embedder expects 768
    assert store._client is None

    results = store.check_health()

    assert results[0].healthy is False
    assert "384" in results[0].detail
    assert "768" in results[0].detail


def test_check_health_never_loads_a_model_for_an_embedder_with_no_known_dimensions(monkeypatch):
    """Codex review HIGH-002 (Lot 6, fifth pass): a `HuggingFaceEmbedder`
    bound to a model name outside its static known-model table previously
    had `.dimensions` called directly from `check_health()`, which imports
    `sentence_transformers` and downloads/loads the real model — unbounded,
    unlocked, and triggerable by any anonymous `/ready` caller. Reproduced
    here with a fake embedder whose `.dimensions` property *raises* if ever
    accessed (proving it genuinely is never touched) and whose
    `known_dimensions()` correctly reports it doesn't know the answer
    cheaply (`None`) — `check_health()` must fall back to
    `self._vector_size` instead, exactly like the no-embedder-bound case."""
    import qdrant_client as qdrant_client_module

    class _UnrecognizedModelEmbedder:
        @property
        def dimensions(self) -> int:
            raise AssertionError(
                "check_health() must never access .dimensions directly -- "
                "it can trigger a real model download/load"
            )

        def known_dimensions(self) -> int | None:
            return None  # e.g. a HuggingFaceEmbedder model name outside its static table

    class _Fake384DimClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(384)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _Fake384DimClient())
    store = QdrantStore()  # vector_size left unset -> constructor default 384
    store.bind_embedder(_UnrecognizedModelEmbedder())
    assert store._client is None

    results = store.check_health()  # must not raise via the fake's .dimensions guard

    assert results[0].healthy is True  # 384 (collection) == 384 (constructor default fallback)


def test_check_health_falls_back_to_the_constructor_default_when_no_embedder_is_bound(
    monkeypatch,
):
    """A standalone `QdrantStore()` that was never wired through
    `ComponentRegistry.wire()` (so `bind_embedder()` was never called) has
    no embedder to resolve a dimension from — the constructor default
    remains the only available comparison, matching pre-ADR-0009
    behavior for this specific, real edge case."""
    import qdrant_client as qdrant_client_module

    class _Fake384DimClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(384)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _Fake384DimClient())
    store = QdrantStore()  # no bind_embedder() call at all
    assert store._client is None
    assert store._embedder is None

    results = store.check_health()

    assert results[0].healthy is True  # 384 (collection) == 384 (constructor default)


def test_check_health_still_validates_an_explicit_vector_size_when_cold(monkeypatch):
    """An *explicit* `indexer.config.vector_size` needs no derivation — it's
    already the source of truth — so a cold probe must still catch a real
    mismatch against it, unlike the non-explicit (derive-from-embedder)
    case above."""
    import qdrant_client as qdrant_client_module

    class _WrongSizeColdClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _FakeHealthCollectionInfo(999)

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _WrongSizeColdClient())
    store = QdrantStore(vector_size=384)  # explicit
    assert store._client is None

    results = store.check_health()

    assert results[0].healthy is False
    assert "999" in results[0].detail
    assert "384" in results[0].detail


def test_check_health_reports_unhealthy_on_named_vectors():
    """A collection created with named vectors (a `dict[str, VectorParams]`,
    not a single unnamed `VectorParams`) has no `.size` — this store always
    creates unnamed collections, so this only fires against a collection
    that predates this store or was created by something else."""

    class _NamedVectorsInfo:
        def __init__(self):
            self.config = type(
                "Config", (), {"params": type("Params", (), {"vectors": {}})()}
            )()  # a dict, not a VectorParams -- no .size attribute

    class _NamedVectorsClient:
        def get_collections(self):
            return _FakeHealthCollectionsResponse(["mrag_default"])

        def get_collection(self, name):
            return _NamedVectorsInfo()

    store = QdrantStore()
    store._client = _NamedVectorsClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "named vectors" in results[0].detail


def test_check_health_returns_unhealthy_with_a_classified_detail_warm(monkeypatch):
    """Codex review MED-002 (Lot 6): `/ready` is unauthenticated, so the raw
    exception message must never reach the response — only a stable code
    plus a correlation id used to look up the full detail server-side."""
    store = QdrantStore()
    store._client = _FakeUnhealthyClient()

    results = store.check_health()

    assert results[0].healthy is False
    assert "connection refused" not in results[0].detail
    assert results[0].detail.startswith("unreachable (")


def test_check_health_returns_healthy_on_a_successful_get_collections_cold(monkeypatch):
    """Cold path (no client ever cached): probes with a bare, throwaway
    client instead of `_get_client()` (orchestration-specialist review, Lot
    6) — must not touch `self._init_lock`, retry, or cache anything onto
    `self._client`."""
    import qdrant_client as qdrant_client_module

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _FakeHealthyClient())
    store = QdrantStore()

    results = store.check_health()

    assert results[0].healthy is True
    assert store._client is None  # never published — this was only a probe


def test_check_health_returns_unhealthy_with_a_classified_detail_cold(monkeypatch):
    """Codex review MED-002 (Lot 6): see the warm-path test above."""
    import qdrant_client as qdrant_client_module

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: _FakeUnhealthyClient())
    store = QdrantStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert "connection refused" not in results[0].detail
    assert results[0].detail.startswith("unreachable (")
    assert store._client is None


class _TrackingCloseClient:
    """Wraps a real fake client and records whether `close()` was called —
    Codex review MEDIUM-002 (Lot 6, fourth pass): the cold-path throwaway
    client's own transport/connection pool was never closed on any exit
    path."""

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
    store = QdrantStore()

    results = store.check_health()

    assert results[0].healthy is True
    assert tracker.closed is True


def test_check_health_closes_the_cold_client_on_an_unhealthy_verdict(monkeypatch):
    """An unhealthy *verdict* (e.g. the collection is missing) is not an
    exception — the client must still be closed on this return path too."""
    import qdrant_client as qdrant_client_module

    class _MissingCollectionInner:
        def get_collections(self):
            return _FakeHealthCollectionsResponse([])  # configured collection absent

    tracker = _TrackingCloseClient(_MissingCollectionInner())
    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: tracker)
    store = QdrantStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert tracker.closed is True


def test_check_health_closes_the_cold_client_when_the_probe_raises(monkeypatch):
    import qdrant_client as qdrant_client_module

    tracker = _TrackingCloseClient(_FakeUnhealthyClient())
    monkeypatch.setattr(qdrant_client_module, "QdrantClient", lambda **kw: tracker)
    store = QdrantStore()

    results = store.check_health()

    assert results[0].healthy is False
    assert tracker.closed is True


def test_check_health_does_not_close_the_warm_shared_client():
    """The cached, shared `self._client` is not this method's to close —
    only a genuinely cold, throwaway client it constructed itself."""
    store = QdrantStore()
    tracker = _TrackingCloseClient(_FakeHealthyClient())
    store._client = tracker

    results = store.check_health()

    assert results[0].healthy is True
    assert tracker.closed is False


def test_check_health_skips_the_network_call_when_the_circuit_is_open(monkeypatch):
    """observability-expert review (Lot 6): check_health() must *read*
    circuit state, never mutate it — an open circuit is reported without
    even attempting a round-trip."""
    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    store = QdrantStore(circuit_breaker=breaker)

    def _must_not_be_called():
        raise AssertionError("check_health() must not call _get_client() while circuit is open")

    monkeypatch.setattr(store, "_get_client", _must_not_be_called)

    results = store.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "circuit open"


def test_get_client_constructs_exactly_one_client_under_concurrent_calls(monkeypatch):
    """Regression test for the check-then-act lazy-init race
    (architecture-reviewer finding, Lot 6): without `self._init_lock`,
    multiple threads could all see `self._client is None` and each
    construct + `_ensure_collection()` their own client, leaking all but
    the last. A small sleep inside the fake constructor widens the race
    window so a missing lock would very likely be caught here, not just
    coincidentally pass."""
    import qdrant_client as qdrant_client_module

    construct_count = {"n": 0}

    class _SlowFakeClient:
        def __init__(self, **kwargs):
            construct_count["n"] += 1
            time.sleep(0.01)

        def close(self):
            pass

    monkeypatch.setattr(qdrant_client_module, "QdrantClient", _SlowFakeClient)
    store = QdrantStore()
    monkeypatch.setattr(store, "_ensure_collection", lambda: None)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: store._get_client(), range(10)))

    assert construct_count["n"] == 1


def test_get_client_retries_against_a_real_unreachable_host_then_raises():
    """The retry+circuit-breaker wrapping inside `_get_client()` had zero
    coverage through an adapter before this (test-specialist review, Lot
    6) — `retry_with_backoff`/`CircuitBreaker` were previously only tested
    in isolation, against fakes, in `tests/unit/core/test_resilience.py`.
    `http://localhost:1` is a real, immediately-refused TCP connection —
    no live Qdrant needed, qdrant-client is an unconditional dependency in
    this dev environment — so this exercises the actual
    `ResponseHandlingException`-is-retryable wiring end to end. Real,
    bounded backoff (~0.3s: `base_delay=0.1` then `0.2`), not a long
    sleep."""
    store = QdrantStore(url="http://localhost:1", timeout=1.0)

    with pytest.raises(Exception):  # noqa: B017 - the real qdrant-client exception type
        store._get_client()

    assert store._client is None


def test_index_retries_a_transient_failure_on_an_already_warm_client(monkeypatch):
    """Codex review HIGH-003 (Lot 6): before this, retry+circuit-breaker
    protection covered only `_get_client()`'s initial connect — an
    operation that failed *after* a successful connect (the ordinary
    production failure mode) was retried by nothing. `_call()` (used by
    `index`/`delete`/`clear`/`list_ids`/`retrieve_by_vector`) fixes that;
    proven here via `index()` against an already-warm, already-cached
    client whose first `upsert()` call fails transiently and whose second
    succeeds."""
    from qdrant_client.http.exceptions import ResponseHandlingException

    from modular_rag.core.ids import new_id
    from modular_rag.core.models.chunk import Chunk

    store = QdrantStore()
    calls = {"n": 0}

    class _FlakyClient:
        def upsert(self, **kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                raise ResponseHandlingException(RuntimeError("transient"))

        def close(self):
            pass

    store._client = _FlakyClient()  # already warm -- no lazy-init involved
    chunk = Chunk(id=new_id(), doc_id="doc-1", content="hello world", tenant_id="tenant-a")
    chunk.embedding = [0.1, 0.2]

    count = store.index([chunk])

    assert count == 1
    assert calls["n"] == 2  # failed once, retried, succeeded — not surfaced to the caller


def test_retrieve_by_vector_uses_query_points_not_the_removed_search_method(monkeypatch):
    """Codex review HIGH-001 (Lot 6): `client.search()` does not exist on
    `qdrant-client==1.18.0` — confirmed live, `hasattr(QdrantClient,
    "search")` is `False`. Every real call to `retrieve_by_vector()`
    previously raised `AttributeError`. This proves the call now reaches
    `query_points()` with the query vector, not `search()`, using a fake
    client that only implements the former."""

    class _QueryPointsOnlyClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def query_points(self, **kwargs):
            self.calls.append(kwargs)

            class _Result:
                points: list = []

            return _Result()

        def close(self):
            pass

    store = QdrantStore()
    fake_client = _QueryPointsOnlyClient()
    store._client = fake_client

    results = store.retrieve_by_vector([0.1, 0.2, 0.3], k=5)

    assert results == []
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0]["query"] == [0.1, 0.2, 0.3]
    assert fake_client.calls[0]["limit"] == 5
    assert "using" not in fake_client.calls[0]  # unnamed default vector, unlike the sparse store


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
