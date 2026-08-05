"""Human-review gate (Lot 11c, docs/refactoring-plan.md — "support human
review for high-risk outcomes").

`threshold` default (0.7) matches the pre-existing documented value in
docs/architecture/security.md's risk-level table ("require_review for
high-risk answers (confidence < 0.7)") — this lot wires that previously
aspirational number into real, callable code.

Honesty note (recorded in the Lot 11c decision record, not hidden here):
today, only `generation.validators.groundedness.GroundednessValidator.refusal_answer()`
sets `Answer.confidence` (to 0.0, on refusal) — no generator scores a
*shipped* answer's confidence yet. This gate is real and will flag whatever
answer sets a low `confidence`, but until a real confidence-scoring path
exists (Lot 13, quality/measurement plane), the only answers it can flag in
practice are refusals — which a reviewer can dismiss quickly, not a defect
in this gate itself.
"""
from __future__ import annotations

import threading

from modular_rag.contracts.review import ReviewItem
from modular_rag.core.errors import ModularRAGError
from modular_rag.core.models.answer import Answer


class HumanReviewGate:
    """In-memory reference `ReviewQueue` implementation. A real, working
    queue (not a mock) — a durable backend follows the same pattern as
    `adapters/audit/postgres_sink.py` once actually needed; not built
    speculatively here.

    Guarded by a `threading.Lock` (Lot 14, docs/refactoring-plan.md — "make
    ... mutable indexes concurrency-safe"): `resolve()` is a read-then-write
    (check the item exists, then replace it) — a real race under concurrent
    resolution attempts for the same item without a lock."""

    def __init__(self, threshold: float = 0.7) -> None:
        self._threshold = threshold
        self._items: dict[str, ReviewItem] = {}
        self._lock = threading.Lock()

    def should_review(self, answer: Answer) -> bool:
        return answer.confidence is not None and answer.confidence < self._threshold

    def enqueue(self, item: ReviewItem) -> None:
        with self._lock:
            self._items[item.id] = item

    def resolve(self, item_id: str, *, approved: bool, reviewer: str) -> None:
        with self._lock:
            if item_id not in self._items:
                raise ModularRAGError(f"No pending review item with id={item_id!r}.")
            item = self._items[item_id]
            self._items[item_id] = item.model_copy(
                update={"resolved": True, "approved": approved, "reviewer": reviewer}
            )

    @property
    def pending(self) -> list[ReviewItem]:
        """Read-only snapshot of unresolved items."""
        with self._lock:
            return [item for item in self._items.values() if not item.resolved]

    def name(self) -> str:
        return "human-review-gate"
