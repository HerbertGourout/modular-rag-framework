"""Unit tests for adapters/embeddings/hf_embedder.py — HuggingFaceEmbedder.

Per ADR-0009 (docs/adr/0009-vector-indexer-dimension-reconciliation.md):
`.dimensions` for a known model must never trigger a real
sentence-transformers model load — verified here by asserting `_model`
stays `None` after access, not just that the returned value is correct.
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.embeddings.hf_embedder import HuggingFaceEmbedder


@pytest.mark.parametrize(
    ("model", "expected_dimensions"),
    [
        ("BAAI/bge-small-en-v1.5", 384),
        ("BAAI/bge-base-en-v1.5", 768),
        ("BAAI/bge-large-en-v1.5", 1024),
        ("sentence-transformers/all-MiniLM-L6-v2", 384),
    ],
)
def test_dimensions_for_a_known_model_does_not_load_the_real_model(model, expected_dimensions):
    embedder = HuggingFaceEmbedder(model=model)

    assert embedder.dimensions == expected_dimensions
    assert embedder._model is None  # never loaded


def test_dimensions_for_an_unrecognized_model_falls_back_to_loading_it(monkeypatch):
    embedder = HuggingFaceEmbedder(model="some/unknown-model")

    class _FakeModel:
        def get_sentence_embedding_dimension(self) -> int:
            return 42

    monkeypatch.setattr(embedder, "_get_model", lambda: _FakeModel())

    assert embedder.dimensions == 42


def test_name_uses_the_model_name_suffix():
    assert HuggingFaceEmbedder(model="BAAI/bge-small-en-v1.5").name() == "hf-bge-small-en-v1.5"
