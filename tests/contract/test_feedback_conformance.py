"""Semantic conformance tests for the FeedbackSink port (contracts/feedback.py).
Batch 14, ADR-0014. Parametrized over `InMemoryFeedbackSink` only.
`PostgresFeedbackSink` requires a real external service — see
`tests/unit/adapters/feedback/test_postgres_sink.py` (mocked pool) and a
future `tests/integration/test_postgres_feedback_sink.py`, mirroring
`.claude/rules/tests.md`'s existing precedent for the audit sink.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.feedback import Feedback, FeedbackRating, FeedbackSink
from modular_rag.security.feedback.store import InMemoryFeedbackSink

SINK_FACTORIES = [InMemoryFeedbackSink]


def _feedback(**overrides: object) -> Feedback:
    defaults: dict[str, object] = {
        "trace_id": "trace-1",
        "idempotency_key": "key-1",
    }
    defaults.update(overrides)
    return Feedback(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_sink_satisfies_the_protocol(sink_factory: type) -> None:
    assert isinstance(sink_factory(), FeedbackSink)


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_record_is_idempotent_on_idempotency_key(sink_factory: type) -> None:
    """Unlike AuditSink.record() (no dedup requirement), FeedbackSink.record()
    must be a no-op on a retried idempotency_key — see the Protocol's own
    docstring."""
    sink = sink_factory()
    feedback = _feedback(rating=FeedbackRating.THUMBS_UP)

    sink.record(feedback)
    sink.record(feedback)  # same idempotency_key — must not duplicate

    assert len(sink.records) == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
async def test_arecord_persists_the_same_way_as_record(sink_factory: type) -> None:
    sink = sink_factory()
    feedback = _feedback(rating=FeedbackRating.THUMBS_DOWN)

    await sink.arecord(feedback)

    assert len(sink.records) == 1  # type: ignore[attr-defined]
    assert sink.records[0].rating == FeedbackRating.THUMBS_DOWN  # type: ignore[attr-defined]


@pytest.mark.parametrize("sink_factory", SINK_FACTORIES)
def test_sink_has_a_name(sink_factory: type) -> None:
    assert sink_factory().name()
