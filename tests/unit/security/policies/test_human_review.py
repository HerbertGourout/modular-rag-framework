"""Unit tests for security/policies/human_review.py — HumanReviewGate. Lot 11c,
docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.review import ReviewItem
from modular_rag.core.errors import ModularRAGError
from modular_rag.core.models.answer import Answer
from modular_rag.security.policies.human_review import HumanReviewGate


def _answer(confidence: float | None) -> Answer:
    return Answer(query_id="q1", text="an answer", confidence=confidence)


def test_should_review_true_below_threshold():
    gate = HumanReviewGate(threshold=0.7)
    assert gate.should_review(_answer(0.5)) is True


def test_should_review_false_at_or_above_threshold():
    gate = HumanReviewGate(threshold=0.7)
    assert gate.should_review(_answer(0.7)) is False
    assert gate.should_review(_answer(0.9)) is False


def test_should_review_false_when_confidence_is_none():
    gate = HumanReviewGate(threshold=0.7)
    assert gate.should_review(_answer(None)) is False


def test_enqueue_adds_to_pending():
    gate = HumanReviewGate()
    item = ReviewItem(answer_id="a1", query_id="q1", reason="low confidence")

    gate.enqueue(item)

    assert len(gate.pending) == 1
    assert gate.pending[0].id == item.id


def test_resolve_marks_item_resolved_and_removes_from_pending():
    gate = HumanReviewGate()
    item = ReviewItem(answer_id="a1", query_id="q1", reason="low confidence")
    gate.enqueue(item)

    gate.resolve(item.id, approved=True, reviewer="alice")

    assert gate.pending == []


def test_resolve_raises_for_unknown_item_id():
    gate = HumanReviewGate()
    with pytest.raises(ModularRAGError):
        gate.resolve("does-not-exist", approved=True, reviewer="alice")


def test_resolve_rejects_a_second_resolution_of_the_same_item():
    """Codex review pass 1, HIGH-002: a terminal transition — resolving an
    already-resolved item must not silently overwrite the first decision's
    `approved`/`reviewer`, matching `PostgresReviewQueue.resolve()`'s
    identical compare-and-set behavior."""
    gate = HumanReviewGate()
    item = ReviewItem(answer_id="a1", query_id="q1", reason="low confidence")
    gate.enqueue(item)
    gate.resolve(item.id, approved=True, reviewer="alice")

    with pytest.raises(ModularRAGError, match="No pending review item"):
        gate.resolve(item.id, approved=False, reviewer="bob")

    # The first decision survives untouched (accessing the internal dict
    # directly since `pending` only exposes unresolved items).
    resolved = gate._items[item.id]
    assert resolved.approved is True
    assert resolved.reviewer == "alice"


def test_name_reports_human_review_gate():
    assert HumanReviewGate().name() == "human-review-gate"
