"""In-memory FeedbackSink reference implementation (Batch 14, ADR-0014). A
real, working sink — not a mock — for tests and local/dev use before a
durable backend (`adapters.feedback.postgres_sink.PostgresFeedbackSink`) is
configured. Mirrors `security.audit.store.InMemoryAuditSink`.
"""
from __future__ import annotations

import threading
from datetime import datetime

from modular_rag.contracts.feedback import Feedback


class InMemoryFeedbackSink:
    """Idempotent on `(tenant_id, idempotency_key)`: a second `record()`
    call with an already-seen key for the same tenant is a silent no-op,
    matching `FeedbackSink`'s Protocol-level idempotency requirement — the
    same property `PostgresFeedbackSink` gets from a unique index scoped
    per tenant (`ux_feedback_tenant_idempotency`). Scoping by tenant, not
    `idempotency_key` alone, prevents one tenant's caller from pre-claiming
    another tenant's key (Batch 14 pass 1 security review finding)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], Feedback] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(feedback: Feedback) -> tuple[str, str]:
        return (feedback.tenant_id or "", feedback.idempotency_key)

    def record(self, feedback: Feedback) -> None:
        with self._lock:
            self._by_key.setdefault(self._key(feedback), feedback)

    async def arecord(self, feedback: Feedback) -> None:
        self.record(feedback)

    def get(self, tenant_id: str | None, idempotency_key: str) -> Feedback | None:
        """Not part of `FeedbackSink`'s Protocol — a concrete-only lookup,
        mirroring `list_since()`'s own non-Protocol-extra pattern. Used by
        `RAGEngine.record_feedback()` to return the record actually stored
        (not a freshly-constructed retry object with a different `id`) on
        an idempotent retry (Codex review pass 1, MEDIUM-001)."""
        with self._lock:
            return self._by_key.get((tenant_id or "", idempotency_key))

    def name(self) -> str:
        return "in-memory"

    @property
    def records(self) -> list[Feedback]:
        """Read-only snapshot for tests/inspection."""
        with self._lock:
            return list(self._by_key.values())

    def list_since(self, since: datetime | None = None) -> list[Feedback]:
        """Not part of `FeedbackSink`'s Protocol — a concrete-only read
        method, mirroring `InMemoryAuditSink.events`/`events_for_
        correlation()`'s own non-Protocol-extra pattern. Matches
        `PostgresFeedbackSink.list_since()`'s signature for
        `scripts/run_drift_check.py`'s sake."""
        with self._lock:
            records = list(self._by_key.values())
        if since is None:
            return records
        return [r for r in records if r.created_at >= since]
