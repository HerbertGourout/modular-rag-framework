"""Unit tests for eval/drift_detection.py. Batch 14, ADR-0014. Pure
functions — no manifest/DB access, so every test here is service-free by
construction."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from modular_rag.contracts.feedback import Feedback, FeedbackRating
from modular_rag.contracts.lifecycle import DocumentRecord
from modular_rag.eval.drift_detection import (
    DriftSnapshot,
    compute_document_freshness,
    compute_drift,
    compute_escalation_metrics,
    compute_feedback_drift_metrics,
    select_feedback_for_reevaluation,
)


def _feedback(**overrides: object) -> Feedback:
    defaults: dict[str, object] = {"trace_id": "t1", "idempotency_key": "k"}
    defaults.update(overrides)
    return Feedback(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_feedback_drift_metrics
# ---------------------------------------------------------------------------


def test_feedback_drift_metrics_empty_input():
    metrics = compute_feedback_drift_metrics([])

    assert metrics.total == 0
    assert metrics.thumbs_up_rate == 0.0
    assert metrics.thumbs_down_rate == 0.0
    assert metrics.empty_retrieval_rate is None


def test_feedback_drift_metrics_computes_rates():
    records = [
        _feedback(idempotency_key="1", rating=FeedbackRating.THUMBS_UP),
        _feedback(idempotency_key="2", rating=FeedbackRating.THUMBS_UP),
        _feedback(idempotency_key="3", rating=FeedbackRating.THUMBS_DOWN),
        _feedback(idempotency_key="4", correction_text="fix this"),
    ]

    metrics = compute_feedback_drift_metrics(records)

    assert metrics.total == 4
    assert metrics.thumbs_up_rate == 0.5
    assert metrics.thumbs_down_rate == 0.25
    assert metrics.correction_rate == 0.25


def test_feedback_drift_metrics_excludes_test_feedback():
    records = [
        _feedback(idempotency_key="1", rating=FeedbackRating.THUMBS_DOWN, is_test=True),
        _feedback(idempotency_key="2", rating=FeedbackRating.THUMBS_UP, is_test=False),
    ]

    metrics = compute_feedback_drift_metrics(records)

    assert metrics.total == 1
    assert metrics.thumbs_up_rate == 1.0
    assert metrics.thumbs_down_rate == 0.0


def test_empty_retrieval_rate_is_none_when_no_case_reports_citation_count():
    metrics = compute_feedback_drift_metrics([_feedback()])

    assert metrics.empty_retrieval_rate is None
    assert metrics.empty_retrieval_coverage == 0


def test_empty_retrieval_rate_distinguishes_zero_from_unreported():
    records = [
        _feedback(idempotency_key="1", citation_count=0),
        _feedback(idempotency_key="2", citation_count=3),
        _feedback(idempotency_key="3"),  # never reported
    ]

    metrics = compute_feedback_drift_metrics(records)

    assert metrics.empty_retrieval_coverage == 2
    assert metrics.empty_retrieval_rate == 0.5


# ---------------------------------------------------------------------------
# compute_document_freshness
# ---------------------------------------------------------------------------


def test_document_freshness_empty_input():
    metrics = compute_document_freshness([])

    assert metrics.total_documents == 0
    assert metrics.stale_document_ratio == 0.0
    assert metrics.oldest_update_age_days is None


def test_document_freshness_computes_stale_ratio():
    now = datetime.now(UTC)
    records = [
        DocumentRecord(
            document_key="fresh", content_hash="h1", updated_at=now - timedelta(days=1)
        ),
        DocumentRecord(
            document_key="stale", content_hash="h2", updated_at=now - timedelta(days=200)
        ),
    ]

    metrics = compute_document_freshness(records, stale_after_days=90, now=now)

    assert metrics.total_documents == 2
    assert metrics.stale_document_ratio == 0.5
    assert metrics.oldest_update_age_days == 200


# ---------------------------------------------------------------------------
# compute_escalation_metrics
# ---------------------------------------------------------------------------


def test_escalation_metrics_rate_uses_total_feedback():
    metrics = compute_escalation_metrics(
        pending_review_count=2, resolved_review_count=8, total_feedback=10
    )

    assert metrics.escalation_rate == 0.2


def test_escalation_metrics_avoids_division_by_zero():
    metrics = compute_escalation_metrics(
        pending_review_count=1, resolved_review_count=0, total_feedback=0
    )

    assert metrics.escalation_rate == 1.0  # 1 / max(0, 1)


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    thumbs_down_rate: float,
    stale_ratio: float = 0.0,
    escalation_rate: float = 0.0,
    empty_retrieval_rate: float | None = None,
) -> DriftSnapshot:
    from modular_rag.eval.drift_detection import (
        DocumentFreshnessMetrics,
        EscalationMetrics,
        FeedbackDriftMetrics,
    )

    return DriftSnapshot(
        feedback=FeedbackDriftMetrics(
            total=100, thumbs_up_rate=1.0 - thumbs_down_rate, thumbs_down_rate=thumbs_down_rate,
            correction_rate=0.0, empty_retrieval_rate=empty_retrieval_rate,
            empty_retrieval_coverage=0 if empty_retrieval_rate is None else 100,
        ),
        freshness=DocumentFreshnessMetrics(
            total_documents=10, stale_document_ratio=stale_ratio, oldest_update_age_days=1.0
        ),
        escalations=EscalationMetrics(
            pending_review_count=0, resolved_review_count=0, escalation_rate=escalation_rate
        ),
    )


def test_compute_drift_no_alerts_when_nothing_degraded():
    baseline = _snapshot(thumbs_down_rate=0.1)
    current = _snapshot(thumbs_down_rate=0.1)

    report = compute_drift(current, baseline)

    assert report.alerts == []
    assert report.should_trigger_retraining is False


def test_compute_drift_flags_a_thumbs_down_rate_increase_past_the_threshold():
    baseline = _snapshot(thumbs_down_rate=0.1)
    current = _snapshot(thumbs_down_rate=0.2)  # +0.10, past the 0.02 default threshold

    report = compute_drift(current, baseline)

    assert any(a.metric == "thumbs_down_rate" for a in report.alerts)
    assert report.should_trigger_retraining is True


def test_compute_drift_does_not_flag_a_change_within_the_tolerance():
    baseline = _snapshot(thumbs_down_rate=0.10)
    current = _snapshot(thumbs_down_rate=0.11)  # +0.01, within the 0.02 default threshold

    report = compute_drift(current, baseline)

    assert report.alerts == []


def test_compute_drift_flags_stale_document_ratio_increase():
    baseline = _snapshot(thumbs_down_rate=0.1, stale_ratio=0.1)
    current = _snapshot(thumbs_down_rate=0.1, stale_ratio=0.3)

    report = compute_drift(current, baseline)

    assert any(a.metric == "stale_document_ratio" for a in report.alerts)
    assert report.should_trigger_retraining is False  # only thumbs_down_rate triggers this flag


def test_compute_drift_flags_escalation_rate_increase():
    baseline = _snapshot(thumbs_down_rate=0.1, escalation_rate=0.05)
    current = _snapshot(thumbs_down_rate=0.1, escalation_rate=0.20)

    report = compute_drift(current, baseline)

    assert any(a.metric == "escalation_rate" for a in report.alerts)


def test_compute_drift_flags_a_thumbs_up_rate_drop():
    # thumbs_up_rate = 1 - thumbs_down_rate, so raising thumbs_down_rate
    # from 0.1 to 0.3 drops thumbs_up_rate by 0.20, past the threshold.
    baseline = _snapshot(thumbs_down_rate=0.1)
    current = _snapshot(thumbs_down_rate=0.3)

    report = compute_drift(current, baseline)

    assert any(a.metric == "thumbs_up_rate" for a in report.alerts)


def test_compute_drift_does_not_flag_a_delta_exactly_at_the_threshold():
    # Strictly greater-than: a delta exactly equal to degradation_threshold
    # must not be flagged. Uses stale_document_ratio (independent of the
    # thumbs_down/up_rate pair — those two move together in `_snapshot()`,
    # so testing the boundary on one of them risks the other landing on
    # the opposite side of its own threshold due to float subtraction
    # noise) with a baseline of 0.0 so the delta is bit-for-bit equal to
    # the same `0.02` literal as the threshold, not a subtraction result.
    baseline = _snapshot(thumbs_down_rate=0.1, stale_ratio=0.0)
    current = _snapshot(thumbs_down_rate=0.1, stale_ratio=0.02)

    report = compute_drift(current, baseline, degradation_threshold=0.02)

    assert report.alerts == []


def test_compute_drift_skips_empty_retrieval_rate_when_either_side_is_none():
    baseline = _snapshot(thumbs_down_rate=0.1, empty_retrieval_rate=None)
    current = _snapshot(thumbs_down_rate=0.1, empty_retrieval_rate=0.9)

    report = compute_drift(current, baseline)

    assert not any(a.metric == "empty_retrieval_rate" for a in report.alerts)


def test_compute_drift_flags_empty_retrieval_rate_increase_when_both_sides_report_it():
    baseline = _snapshot(thumbs_down_rate=0.1, empty_retrieval_rate=0.1)
    current = _snapshot(thumbs_down_rate=0.1, empty_retrieval_rate=0.4)

    report = compute_drift(current, baseline)

    assert any(a.metric == "empty_retrieval_rate" for a in report.alerts)
    assert report.should_trigger_retraining is False  # only thumbs_down_rate triggers this flag


# ---------------------------------------------------------------------------
# select_feedback_for_reevaluation
# ---------------------------------------------------------------------------


def test_select_feedback_for_reevaluation_only_returns_records_with_a_correction():
    records = [
        _feedback(idempotency_key="1", correction_text="the real answer"),
        _feedback(idempotency_key="2", rating=FeedbackRating.THUMBS_UP),
        _feedback(idempotency_key="3", correction_text="another correction", is_test=True),
    ]

    selected = select_feedback_for_reevaluation(records)

    assert len(selected) == 1
    assert selected[0].idempotency_key == "1"
