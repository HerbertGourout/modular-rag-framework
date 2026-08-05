"""Unit tests for adapters/embeddings/openai_embedder.py — OpenAIEmbedder.
No prior direct unit coverage existed. Scoped to Lot 14
(docs/refactoring-plan.md — "timeouts", "own and close clients/resources");
a full characterization pass on `embed()`/`aembed()` themselves is separate
scope.
"""
from __future__ import annotations

from modular_rag.adapters.embeddings.openai_embedder import OpenAIEmbedder


def test_default_timeout_is_thirty_seconds():
    assert OpenAIEmbedder()._timeout == 30.0


def test_get_client_passes_timeout_to_the_real_openai_client():
    embedder = OpenAIEmbedder(api_key="sk-test", timeout=5.0)

    client = embedder._get_client()

    assert client.timeout == 5.0


def test_close_releases_the_client_if_one_was_opened():
    embedder = OpenAIEmbedder(api_key="sk-test")
    embedder._get_client()
    assert embedder._client is not None

    embedder.close()

    assert embedder._client is None


def test_close_is_a_no_op_when_no_client_was_ever_opened():
    OpenAIEmbedder().close()  # must not raise
