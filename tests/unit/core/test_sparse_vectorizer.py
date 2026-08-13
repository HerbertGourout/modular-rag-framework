"""Unit tests for core/sparse_vectorizer.py (Lot 5, persistent sparse retrieval).

retrieval-specialist review: index-time (`index_sparse_vector`, saturated
BM25 term-frequency) and query-time (`query_sparse_vector`, flat presence)
weighting are deliberately different functions sharing one tokenizer/hasher —
these tests pin both the difference and the shared hash space.
"""
from __future__ import annotations

import hashlib

import pytest

from modular_rag.core.sparse_vectorizer import (
    hash_term,
    index_sparse_vector,
    query_sparse_vector,
    tokenize,
)


def test_tokenize_lowercases_and_splits_on_word_boundaries():
    assert tokenize("Blue Whales, largest animals!") == ["blue", "whales", "largest", "animals"]


def test_tokenize_empty_string_yields_no_tokens():
    assert tokenize("") == []


def test_hash_term_is_deterministic():
    assert hash_term("whale") == hash_term("whale")


def test_hash_term_differs_for_different_tokens():
    assert hash_term("whale") != hash_term("shark")


def test_hash_term_stays_within_the_unsigned_32_bit_space():
    assert 0 <= hash_term("whale") < 2**32


def test_hash_term_pins_the_exact_algorithm():
    """test-specialist review (Lot 5): `int.from_bytes(digest[:4], "big")`
    is already `< 2**32` by construction, so a bare range assertion
    (`test_hash_term_stays_within_the_unsigned_32_bit_space` above) can
    never fail regardless of what the function does — it doesn't pin the
    algorithm at all. This test recomputes the hash independently (SHA256,
    first 4 bytes, big-endian, no modulo needed) so a future change to the
    hashing scheme is actually caught, not silently accepted."""
    token = "whale"
    expected = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big")

    assert hash_term(token) == expected


def test_index_sparse_vector_of_empty_content_is_empty():
    assert index_sparse_vector("", avgdl=128.0) == {}


def test_index_sparse_vector_of_content_with_no_word_tokens_is_empty():
    assert index_sparse_vector("!!! ??? ...", avgdl=128.0) == {}


def test_index_sparse_vector_has_one_entry_per_distinct_token():
    vector = index_sparse_vector("blue whales are the largest animals", avgdl=128.0)

    assert len(vector) == 6  # 6 distinct tokens, none repeated


def test_index_sparse_vector_weight_increases_with_term_frequency_but_saturates():
    """BM25's saturated-TF term is monotonically increasing in raw term
    frequency but sub-linear (each repeat adds less than the last) — unlike
    raw term frequency, which the retrieval-specialist review flagged as
    wrong for this use (loses saturation, over-rewards repetition).

    test-specialist review (Lot 5): document length (`dl`) is held constant
    across all three documents (all 3 tokens) so only `tf` varies — the
    original version of this test varied `dl` alongside `tf`
    ("whale fish bird" -> "whale whale fish bird" -> ...), which still
    happened to pass but confounded the two effects instead of isolating
    saturation specifically."""
    once = index_sparse_vector("whale filler filler", avgdl=128.0)
    twice = index_sparse_vector("whale whale filler", avgdl=128.0)
    thrice = index_sparse_vector("whale whale whale", avgdl=128.0)

    whale_index = hash_term("whale")
    w1, w2, w3 = once[whale_index], twice[whale_index], thrice[whale_index]

    assert w1 < w2 < w3
    # Sub-linear: the jump from tf=2->3 must be smaller than tf=1->2.
    assert (w3 - w2) < (w2 - w1)


def test_index_sparse_vector_pins_the_k1_constant_at_dl_equal_avgdl():
    """test-specialist review (Lot 5): the qualitative assertions above
    (monotone + sub-linear in tf, decreasing in dl) are satisfied by several
    formulas that are *not* BM25 — verified 9 of 11 hand-written mutants
    (k1/b hardcoded and ignored, missing (k1+1) numerator term, an
    unrelated log1p formula) pass every assertion in this file before this
    test was added. At dl == avgdl the length-normalization term
    (1 - b + b*dl/avgdl) collapses to exactly 1 regardless of `b`, isolating
    `k1`'s contribution — golden value computed by hand for the default
    k1=1.2: tf*(k1+1)/(tf+k1) = 1*2.2/2.2 == 1.0 exactly."""
    vector = index_sparse_vector("a", avgdl=1.0)  # dl == avgdl == 1

    assert vector[hash_term("a")] == pytest.approx(1.0)


def test_index_sparse_vector_pins_the_b_constant_when_dl_differs_from_avgdl():
    """dl=2, avgdl=1 makes the length-normalization term depend on `b`
    directly — golden value computed by hand for the default b=0.75, k1=1.2:
    tf*(k1+1) / (tf + k1*(1 - b + b*dl/avgdl)) = 2.2 / 3.1."""
    vector = index_sparse_vector("a b", avgdl=1.0)  # dl=2, tf("a")=1

    assert vector[hash_term("a")] == pytest.approx(2.2 / 3.1)


def test_index_sparse_vector_respects_non_default_k1_and_b():
    """test-specialist review (Lot 5): no other test in this file — and no
    test anywhere in the QdrantSparseStore layer either — ever passes a
    non-default `k1`/`b`, so a transposed or silently-ignored parameter
    (e.g. `k1=self._b` inside QdrantSparseStore.index()) would be invisible
    to the whole suite. Expected value re-derives the formula independently
    (not by calling the function under test) with different literal
    constants than the implementation's own defaults."""
    default = index_sparse_vector("a b", avgdl=1.0)
    tuned = index_sparse_vector("a b", avgdl=1.0, k1=2.4, b=0.5)

    assert default[hash_term("a")] != tuned[hash_term("a")]
    tf, dl, avgdl, k1, b = 1, 2, 1.0, 2.4, 0.5
    expected = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
    assert tuned[hash_term("a")] == pytest.approx(expected)


def test_index_sparse_vector_penalizes_a_longer_document_at_equal_term_frequency():
    """`b` (length-normalization) parameter: the same term, same raw
    frequency, in a document far longer than avgdl must score lower than in
    a document at avgdl — otherwise no length normalization is happening."""
    short_avgdl = index_sparse_vector("whale fish bird", avgdl=3.0)
    padded = "whale fish bird " + "padding " * 100
    long_doc = index_sparse_vector(padded, avgdl=3.0)

    whale_index = hash_term("whale")
    assert long_doc[whale_index] < short_avgdl[whale_index]


def test_query_sparse_vector_weights_every_distinct_term_at_one():
    vector = query_sparse_vector("whale whale fish")

    assert set(vector.values()) == {1.0}
    assert len(vector) == 2  # "whale" (repeated) + "fish"


def test_query_sparse_vector_of_empty_text_is_empty():
    assert query_sparse_vector("") == {}


def test_index_and_query_vectors_share_the_same_hash_space_for_a_shared_term():
    """The core correctness property this whole module exists for: the same
    token must land on the same index whether it was hashed at index time or
    query time, or search finds nothing even for an exact term match."""
    indexed = index_sparse_vector("blue whales swim", avgdl=128.0)
    queried = query_sparse_vector("whales")

    assert hash_term("whales") in indexed
    assert hash_term("whales") in queried
    assert set(queried) <= set(indexed)
