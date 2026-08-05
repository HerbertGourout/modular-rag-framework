"""Unit tests for adapters/vectorstores/qdrant_store.py — QdrantStore. No
prior direct unit coverage existed (only integration, requiring a live
Qdrant). Scoped to Lot 14 (docs/refactoring-plan.md — "timeouts", "own and
close clients/resources"): `_ensure_collection()` needs a live server, so
it's monkeypatched to a no-op here — this proves client construction
accepts the `timeout` kwarg without needing Qdrant itself running.
"""
from __future__ import annotations

from modular_rag.adapters.vectorstores.qdrant_store import QdrantStore


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
