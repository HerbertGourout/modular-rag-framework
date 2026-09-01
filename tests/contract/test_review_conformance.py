"""Semantic conformance tests for the ReviewQueue port (contracts/review.py).
Lot 11c, docs/refactoring-plan.md — "support human review for high-risk
outcomes". Behavioral tests are parametrized over `HumanReviewGate`
(in-memory, no external service). `PostgresReviewQueue` (Batch 14,
ADR-0014) is covered by a separate, unparametrized Protocol-only check
below — unlike behavior (`enqueue`/`resolve`/`pending`), which needs a real
database (see `tests/unit/adapters/review/test_postgres_queue.py` for
mocked-pool coverage and a future `tests/integration/
test_postgres_review_queue.py`), `isinstance(obj, ReviewQueue)` is free:
`PostgresReviewQueue.__init__` takes a DSN and opens no connection.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.review import ReviewItem, ReviewQueue
from modular_rag.core.errors import ModularRAGError
from modular_rag.core.models.answer import Answer
from modular_rag.security.policies.human_review import HumanReviewGate

QUEUES = [HumanReviewGate]


def test_postgres_review_queue_satisfies_the_protocol() -> None:
    from modular_rag.adapters.review.postgres_queue import PostgresReviewQueue

    assert isinstance(PostgresReviewQueue(dsn="postgresql://unused/unused"), ReviewQueue)


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
