"""Human-review contract (Lot 11c, docs/refactoring-plan.md — "support human
review for high-risk outcomes").

Distinct from `contracts.audit.AuditSink`: an `AuditEvent` is an immutable
compliance record of what happened; a `ReviewItem` is a *pending task* —
something a human is expected to act on (approve/reject), with a mutable
resolution state. Keeping them separate avoids overloading one contract with
both "what happened" and "what needs to happen next."
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer


class ReviewItem(BaseModel):
    id: str = Field(default_factory=new_id)
    answer_id: str
    query_id: str
    tenant_id: str | None = None
    reason: str
    confidence: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    approved: bool | None = None
    reviewer: str | None = None


@runtime_checkable
class ReviewQueue(Protocol):
    """Gate high-risk answers for human review, and hold them until resolved.
    `security.policies.human_review.HumanReviewGate` is the reference
    implementation; registered on `Container.review_queue` — optional,
    mirrors `guard`/`audit_sink`/`tenant_policy`'s optionality."""

    def should_review(self, answer: Answer) -> bool: ...

    def enqueue(self, item: ReviewItem) -> None: ...

    def resolve(self, item_id: str, *, approved: bool, reviewer: str) -> None: ...

    def name(self) -> str: ...
