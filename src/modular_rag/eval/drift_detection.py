"""Offline drift detection (Batch 14, external plan — "Feedback, drift, and
human review"; ADR-0014). The exact module path `ROADMAP.md`'s V3.2 already
names.

Pure computation only: every function here takes plain data
(`list[Feedback]`, `list[DocumentRecord]`, review-queue counts) and returns
plain result objects. Nothing in this module opens a database connection,
loads a manifest, or is reachable from any runtime pipeline component — per
ADR-0008, drift detection stays a native, offline, script-driven capability,
never a blocking online gate. `scripts/run_drift_check.py` (outside
`src/modular_rag/`, for the same layering reason `scripts/run_benchmark.py`
lives there) is what actually wires a manifest, reads the durable stores,
and calls the functions below.

`is_test=True` feedback (ADR-0014 decision 6) is excluded from every
aggregation in this module by default — synthetic/QA traffic must not skew
a real drift signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from modular_rag.contracts.feedback import Feedback, FeedbackRating
from modular_rag.contracts.lifecycle import DocumentRecord


def _real_feedback(records: list[Feedback]) -> list[Feedback]:
    return [f for f in records if not f.is_test]


@dataclass(frozen=True)
class FeedbackDriftMetrics:
    """Aggregate signal over a window of real (non-test) feedback."""

    total: int
    thumbs_up_rate: float
    thumbs_down_rate: float
    correction_rate: float
    # None when no feedback in the window reported citation_count at all —
    # distinct from 0.0 (every reporting case had zero citations). See
    # ADR-0014's "Explicitly out of scope" note on why this is
    # caller-reported, not new backend telemetry.
    empty_retrieval_rate: float | None
    empty_retrieval_coverage: int


def compute_feedback_drift_metrics(records: list[Feedback]) -> FeedbackDriftMetrics:
    real = _real_feedback(records)
    total = len(real)
    if total == 0:
        return FeedbackDriftMetrics(
            total=0,
            thumbs_up_rate=0.0,
            thumbs_down_rate=0.0,
            correction_rate=0.0,
            empty_retrieval_rate=None,
            empty_retrieval_coverage=0,
        )
    thumbs_up = sum(1 for f in real if f.rating == FeedbackRating.THUMBS_UP)
    thumbs_down = sum(1 for f in real if f.rating == FeedbackRating.THUMBS_DOWN)
    corrections = sum(1 for f in real if f.correction_text)
    with_citation_count = [f for f in real if f.citation_count is not None]
    empty_retrieval_rate = (
        sum(1 for f in with_citation_count if f.citation_count == 0) / len(with_citation_count)
        if with_citation_count
        else None
    )
    return FeedbackDriftMetrics(
        total=total,
        thumbs_up_rate=thumbs_up / total,
        thumbs_down_rate=thumbs_down / total,
        correction_rate=corrections / total,
        empty_retrieval_rate=empty_retrieval_rate,
        empty_retrieval_coverage=len(with_citation_count),
    )


@dataclass(frozen=True)
class DocumentFreshnessMetrics:
    """Corpus staleness, derived from `LifecycleLedger` records
    (`DocumentRecord.updated_at`)."""

    total_documents: int
    stale_document_ratio: float
    oldest_update_age_days: float | None


def compute_document_freshness(
    records: list[DocumentRecord], *, stale_after_days: int = 90, now: datetime | None = None
) -> DocumentFreshnessMetrics:
    as_of = now or datetime.now(UTC)
    total = len(records)
    if total == 0:
        return DocumentFreshnessMetrics(
            total_documents=0, stale_document_ratio=0.0, oldest_update_age_days=None
        )
    ages_days = [(as_of - r.updated_at).total_seconds() / 86400 for r in records]
    stale = sum(1 for age in ages_days if age > stale_after_days)
    return DocumentFreshnessMetrics(
        total_documents=total,
        stale_document_ratio=stale / total,
        oldest_update_age_days=max(ages_days),
    )


@dataclass(frozen=True)
class EscalationMetrics:
    """Human-review-queue signal (`ReviewQueue.pending`, plus caller-supplied
    counts — this module never queries a queue directly)."""

    pending_review_count: int
    resolved_review_count: int
    escalation_rate: float  # pending / max(total_feedback, 1)


def compute_escalation_metrics(
    *, pending_review_count: int, resolved_review_count: int, total_feedback: int
) -> EscalationMetrics:
    return EscalationMetrics(
        pending_review_count=pending_review_count,
        resolved_review_count=resolved_review_count,
        escalation_rate=pending_review_count / max(total_feedback, 1),
    )


@dataclass(frozen=True)
class DriftSnapshot:
    """One point-in-time bundle of every drift-adjacent signal — the unit
    `compute_drift()` compares two of (current vs. baseline)."""

    feedback: FeedbackDriftMetrics
    freshness: DocumentFreshnessMetrics
    escalations: EscalationMetrics
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DriftAlert:
    metric: str
    baseline: float
    current: float
    delta: float


@dataclass(frozen=True)
class DriftReport:
    snapshot: DriftSnapshot
    alerts: list[DriftAlert]
    should_trigger_retraining: bool


def compute_drift(
    current: DriftSnapshot,
    baseline: DriftSnapshot,
    *,
    degradation_threshold: float = 0.02,
) -> DriftReport:
    """Compare `current` against `baseline`. `degradation_threshold` matches
    ROADMAP.md V3.2's own literal wording ("alert if degrading > 2%").
    `should_trigger_retraining` is an advisory flag only — nothing in this
    codebase acts on it; per ADR-0005 §5.2, deciding to retrain stays
    native, executing a retraining job is delegated to external MLOps
    tooling this framework never invokes."""
    alerts: list[DriftAlert] = []

    def _check(name: str, baseline_value: float, current_value: float, *, lower_is_better: bool) -> None:
        delta = current_value - baseline_value
        degraded = delta > degradation_threshold if lower_is_better else delta < -degradation_threshold
        if degraded:
            alerts.append(
                DriftAlert(metric=name, baseline=baseline_value, current=current_value, delta=delta)
            )

    _check(
        "thumbs_down_rate",
        baseline.feedback.thumbs_down_rate,
        current.feedback.thumbs_down_rate,
        lower_is_better=True,
    )
    _check(
        "thumbs_up_rate",
        baseline.feedback.thumbs_up_rate,
        current.feedback.thumbs_up_rate,
        lower_is_better=False,
    )
    if (
        current.feedback.empty_retrieval_rate is not None
        and baseline.feedback.empty_retrieval_rate is not None
    ):
        _check(
            "empty_retrieval_rate",
            baseline.feedback.empty_retrieval_rate,
            current.feedback.empty_retrieval_rate,
            lower_is_better=True,
        )
    _check(
        "stale_document_ratio",
        baseline.freshness.stale_document_ratio,
        current.freshness.stale_document_ratio,
        lower_is_better=True,
    )
    _check(
        "escalation_rate",
        baseline.escalations.escalation_rate,
        current.escalations.escalation_rate,
        lower_is_better=True,
    )

    should_trigger_retraining = any(a.metric == "thumbs_down_rate" for a in alerts)
    return DriftReport(snapshot=current, alerts=alerts, should_trigger_retraining=should_trigger_retraining)


def select_feedback_for_reevaluation(records: list[Feedback]) -> list[Feedback]:
    """Select feedback carrying a human-provided `correction_text` — in
    effect, an ad-hoc gold answer for that one query — as candidates for
    offline re-evaluation. Selection only: this does not re-score anything
    (see ADR-0014's "Explicitly out of scope" note on why — the original
    answer text/citations are not durably persisted anywhere in this
    codebase today, so there is nothing yet to re-score against). Excludes
    `is_test=True` records, matching every other aggregation in this
    module."""
    return [f for f in _real_feedback(records) if f.correction_text]
