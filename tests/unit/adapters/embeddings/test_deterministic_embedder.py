"""Unit tests for adapters/embeddings/deterministic_embedder.py.

Lot 4 (secure preset e2e correction): this embedder exists specifically so
an e2e/integration test can wire a real, contract-conformant `Embedder`
without a model download or API key — these tests pin the properties that
guarantee, including across a genuine process restart (sha256 has no
run-to-run variance, unlike Python's salted `hash()`).
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.embeddings.deterministic_embedder import DeterministicEmbedder
from modular_rag.core.errors import ConfigurationError


def test_dimensions_defaults_to_256():
    assert DeterministicEmbedder().dimensions == 256


def test_dimensions_is_configurable():
    assert DeterministicEmbedder(dimensions=32).dimensions == 32


@pytest.mark.parametrize("dimensions", [0, -1, -256])
def test_non_positive_dimensions_is_rejected_at_construction(dimensions):
    """Codex review: previously wired/validated successfully, then crashed
    with ZeroDivisionError/IndexError deep inside embed() on first real use."""
    with pytest.raises(ConfigurationError, match=str(dimensions)):
        DeterministicEmbedder(dimensions=dimensions)


def test_embed_returns_a_vector_of_the_configured_length():
    embedder = DeterministicEmbedder(dimensions=32)

    vectors = embedder.embed(["hello world"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 32


def test_embed_is_deterministic_across_separate_instances():
    """The property the whole e2e restart scenario depends on: two
    independently constructed embedders (standing in for two separate
    process runs) must produce byte-identical vectors for the same text."""
    text = "The quick brown fox jumps over the lazy dog."

    a = DeterministicEmbedder().embed([text])[0]
    b = DeterministicEmbedder().embed([text])[0]

    assert a == b


def test_embed_is_case_insensitive():
    a = DeterministicEmbedder().embed(["Hello World"])[0]
    b = DeterministicEmbedder().embed(["hello world"])[0]

    assert a == b


def test_embed_vectors_are_unit_normalized():
    vector = DeterministicEmbedder().embed(["some reasonably long sentence of text"])[0]

    norm = sum(v * v for v in vector) ** 0.5

    assert abs(norm - 1.0) < 1e-9


def test_embed_of_empty_text_returns_a_usable_non_zero_vector():
    """Cosine distance (Qdrant's default here) is undefined for an all-zero
    vector — the degenerate-input fallback must never return one."""
    vector = DeterministicEmbedder().embed([""])[0]

    norm = sum(v * v for v in vector) ** 0.5

    assert norm > 0.0


def test_shared_vocabulary_increases_cosine_similarity():
    """Not a claim of semantic quality — just the hashing-trick property the
    e2e scenario relies on: texts sharing more words land closer together in
    cosine space than texts sharing none."""
    embedder = DeterministicEmbedder()

    def _cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))  # both already unit-normalized

    base = "quarterly revenue report shows strong growth"
    similar = "quarterly revenue report shows modest growth"
    unrelated = "purple elephants dance under moonlight silently"

    v_base, v_similar, v_unrelated = embedder.embed([base, similar, unrelated])

    assert _cosine(v_base, v_similar) > _cosine(v_base, v_unrelated)


def test_embed_multiple_texts_preserves_order():
    embedder = DeterministicEmbedder(dimensions=16)

    vectors = embedder.embed(["first", "second", "third"])

    assert vectors[0] == embedder.embed(["first"])[0]
    assert vectors[2] == embedder.embed(["third"])[0]


def test_aembed_matches_embed():
    import asyncio

    embedder = DeterministicEmbedder()
    text = "async and sync paths must agree"

    sync_result = embedder.embed([text])
    async_result = asyncio.run(embedder.aembed([text]))

    assert sync_result == async_result


def test_name_is_stable_identifier():
    assert DeterministicEmbedder().name() == "deterministic"
