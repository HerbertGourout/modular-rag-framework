"""Tests for contracts/erasure.py — ErasureProof.fully_verified. Lot 12c,
docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.erasure import ErasureProof


def _proof(**overrides) -> ErasureProof:
    defaults = {
        "document_key": "key-1",
        "verified_absent_from_vector": True,
        "verified_absent_from_lexical": True,
        "proof_hash": "abc123",
    }
    defaults.update(overrides)
    return ErasureProof(**defaults)


def test_fully_verified_true_when_both_stores_confirm_absence():
    assert _proof().fully_verified is True


def test_fully_verified_false_when_vector_still_has_it():
    assert _proof(verified_absent_from_vector=False).fully_verified is False


def test_fully_verified_false_when_lexical_still_has_it():
    assert _proof(verified_absent_from_lexical=False).fully_verified is False


def test_fully_verified_true_when_lexical_could_not_be_checked():
    """None (unverifiable) is not treated as a failure — but also isn't
    silently upgraded to True elsewhere; see the field's own docstring."""
    assert _proof(verified_absent_from_lexical=None).fully_verified is True
