"""Tests for contracts/feedback.py — Feedback defaults. Batch 14, ADR-0014."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from modular_rag.contracts.feedback import Feedback, FeedbackRating


def test_feedback_defaults():
    feedback = Feedback(trace_id="t1", idempotency_key="k1")
    assert feedback.id
    assert feedback.schema_version == "1.0"
    assert feedback.tenant_id is None
    assert feedback.rating is None
    assert feedback.correction_text is None
    assert feedback.citation_count is None
    assert feedback.submitted_by is None
    assert feedback.is_test is False
    assert feedback.retention_days == 365


def test_feedback_with_rating_and_correction():
    feedback = Feedback(
        trace_id="t1",
        idempotency_key="k1",
        rating=FeedbackRating.THUMBS_DOWN,
        correction_text="the actual answer is 30 days",
        citation_count=0,
        is_test=True,
    )
    assert feedback.rating == FeedbackRating.THUMBS_DOWN
    assert feedback.correction_text == "the actual answer is 30 days"
    assert feedback.citation_count == 0
    assert feedback.is_test is True


# ---------------------------------------------------------------------------
# Codex review pass 1, MEDIUM-002.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_trace_id_is_rejected(blank: str) -> None:
    with pytest.raises(ValidationError, match="blank"):
        Feedback(trace_id=blank, idempotency_key="k1")


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_idempotency_key_is_rejected(blank: str) -> None:
    with pytest.raises(ValidationError, match="blank"):
        Feedback(trace_id="t1", idempotency_key=blank)


def test_negative_citation_count_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Feedback(trace_id="t1", idempotency_key="k1", citation_count=-1)


def test_zero_citation_count_is_allowed() -> None:
    feedback = Feedback(trace_id="t1", idempotency_key="k1", citation_count=0)
    assert feedback.citation_count == 0
