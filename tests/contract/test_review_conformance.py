"""Semantic conformance tests for the ReviewQueue port (contracts/review.py).
Lot 11c, docs/refactoring-plan.md — "support human review for high-risk
outcomes". Parametrized over `HumanReviewGate`, the only implementation.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.review import ReviewItem, ReviewQueue
from modular_rag.core.errors import ModularRAGError
from modular_rag.core.models.answer import Answer
from modular_rag.security.policies.human_review import HumanReviewGate

QUEUES = [HumanReviewGate]


@pytest.mark.parametrize("queue_factory", QUEUES)
def test_queue_satisfies_the_protocol(queue_factory):
    assert isinstance(queue_factory(), ReviewQueue)


@pytest.mark.parametrize("queue_factory", QUEUES)
def test_should_review_is_threshold_gated(queue_factory):
    queue = queue_factory(threshold=0.5)
    assert queue.should_review(Answer(query_id="q1", text="x", confidence=0.1)) is True
    assert queue.should_review(Answer(query_id="q1", text="x", confidence=0.9)) is False


@pytest.mark.parametrize("queue_factory", QUEUES)
def test_enqueue_then_resolve_removes_from_pending(queue_factory):
    queue = queue_factory()
    item = ReviewItem(answer_id="a1", query_id="q1", reason="low confidence")

    queue.enqueue(item)
    assert len(queue.pending) == 1

    queue.resolve(item.id, approved=True, reviewer="alice")
    assert queue.pending == []


@pytest.mark.parametrize("queue_factory", QUEUES)
def test_resolve_raises_for_an_unknown_item(queue_factory):
    with pytest.raises(ModularRAGError):
        queue_factory().resolve("unknown-id", approved=False, reviewer="alice")


@pytest.mark.parametrize("queue_factory", QUEUES)
def test_queue_has_a_name(queue_factory):
    assert queue_factory().name()
