"""User-feedback contract (Batch 14, external plan — "Feedback, drift, and
human review"; ADR-0014).

Distinct from `contracts.review.ReviewItem`: a `ReviewItem` is a pending task
the *pipeline* raised (a low-confidence answer flagged before it ever reached
the caller); `Feedback` is a signal the *caller* volunteers after receiving an
answer (a rating, a correction). Distinct from `contracts.audit.AuditEvent`:
an `AuditEvent` records what the pipeline did; `Feedback` records what a user
thought of the result. All three are durable, retention-bearing governance
records that share the same storage pattern (see `contracts.audit.AuditSink`)
without sharing a contract — each answers a different question.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from modular_rag.core.ids import new_id

FEEDBACK_SCHEMA_VERSION = "1.0"


class FeedbackRating(StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class Feedback(BaseModel):
    """One user-submitted feedback record.

    `trace_id` is required and is the only identifier this framework
    currently returns to an API caller (`Answer.trace_id`, surfaced as
    `AnswerResponse.trace_id`) — see ADR-0014's Context section for why
    `request_id`/`correlation_id` are not usable here (neither ever leaves
    the process today). `idempotency_key` is required and is the sink's
    dedup key, scoped per tenant (`tenant_id`, `idempotency_key`) — a
    retried submission with the same key for the same tenant is a silent
    no-op, not an error, the same "retry-safe write" property
    `contracts.audit.AuditEvent.id` + `ON CONFLICT DO NOTHING` already gives
    audit events. Scoping by tenant (not `idempotency_key` alone) prevents
    one tenant's caller from pre-claiming another tenant's key.

    `correction_text`, if present, is expected to already be redacted by the
    time a `Feedback` reaches a `FeedbackSink.record()` call —
    `orchestration.engine.RAGEngine.record_feedback()` enforces this before
    ever constructing one (ADR-0014 decision 5); no `FeedbackSink`
    implementation redacts on its own.

    `is_test`, if `True`, marks this record as synthetic/QA traffic —
    `eval.drift_detection` excludes it from real drift aggregation by
    default. Only an authenticated caller whose identity carries the
    `"tester"` role may set it; enforced by `app.application.
    ApplicationService.record_feedback()`, not this model (ADR-0014
    decision 6).

    `trace_id`/`idempotency_key` reject a blank or whitespace-only string
    and `citation_count` rejects a negative value (Codex review pass 1,
    MEDIUM-002) — a blank identifier links to nothing and a negative count
    is not a real citation count, so both are rejected at construction
    rather than silently persisted and counted in drift aggregation.
    Deliberately **not** enforced here: that at least one of `rating`/
    `correction_text` is present. `test_feedback_defaults()` (`tests/unit/
    contracts/test_feedback.py`) and roughly a dozen other call sites across
    this batch's own test suite construct a signal-free `Feedback` on
    purpose to exercise idempotency/storage/aggregation mechanics unrelated
    to signal content — requiring a signal would force touching all of them
    for no change in what each actually verifies. Left as a deferred,
    separately-scoped follow-up (pass 2 closure handoff), not silently
    dropped.
    """

    id: str = Field(default_factory=new_id)
    schema_version: str = FEEDBACK_SCHEMA_VERSION
    trace_id: str
    tenant_id: str | None = None
    rating: FeedbackRating | None = None
    correction_text: str | None = None
    # Caller-reported count of citations the answer being rated actually had
    # — the caller already has this when rendering a feedback widget next to
    # an answer. Powers eval.drift_detection's empty-retrieval signal without
    # new backend telemetry (ADR-0014 decision 7 / "Explicitly out of scope").
    citation_count: int | None = Field(default=None, ge=0)
    idempotency_key: str
    submitted_by: str | None = None
    is_test: bool = False
    retention_days: int = Field(default=365, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("trace_id", "idempotency_key")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank or whitespace-only")
        return value


@runtime_checkable
class FeedbackSink(Protocol):
    """Persist `Feedback` records. `security.feedback.store.InMemoryFeedbackSink`
    is the reference implementation; `adapters.feedback.postgres_sink.
    PostgresFeedbackSink` is the durable backend. Registered on
    `Container.feedback_sink` — optional, mirrors `audit_sink`/`review_queue`'s
    existing optionality.

    `record()` must be idempotent on `(Feedback.tenant_id, Feedback.
    idempotency_key)`: calling it twice with the same key for the same
    tenant stores the record once. A different tenant may reuse the same
    `idempotency_key` without colliding."""

    def record(self, feedback: Feedback) -> None: ...

    async def arecord(self, feedback: Feedback) -> None: ...

    def name(self) -> str: ...
