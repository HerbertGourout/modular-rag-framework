"""Compliance-audit event contract (Lot 10, docs/refactoring-plan.md).

Deliberately separate from `core.models.trace.Trace`/`TraceStep`: a Trace is
execution/performance observability (latency, token counts, step names) —
an `AuditEvent` is compliance evidence (who did what, to which tenant's
data, when), with an explicit allowlist on its payload so PII/secrets can't
leak into audit storage just because a caller passed them in. This mirrors
`.claude/.instructions.md` §2 "Safety ≠ Security": Trace is observability,
AuditEvent is the audit-trail half of V1.2 (`CLAUDE.md` §09), owned
natively per ADR-0005 §5.1.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from modular_rag.core.ids import new_id

AUDIT_SCHEMA_VERSION = "1.0"

# Payload keys an AuditEvent is allowed to carry. An explicit allowlist, not
# a denylist: a new sensitive field introduced elsewhere in the codebase
# must be deliberately added here before it can reach audit storage, rather
# than silently passing through because nobody thought to denylist it yet.
ALLOWED_PAYLOAD_KEYS = frozenset({
    "query_text_redacted",  # never the raw query — redaction happens before this is built
    "chunk_ids",
    "answer_length",
    "citation_count",
    "guard_decision",
    "guard_reason",
    "policy_refs",
    "model_name",
    "latency_ms",
    "error_type",
    # Lot 20 (docs/refactoring-plan.md): egress-decision evidence. Content-free by
    # construction (EgressDecision, contracts/egress.py) -- never the classified
    # query/chunk/document text, only what was decided and against what provider/operation.
    "egress_decision",
    "egress_reason",
    "egress_provider",
    "egress_classification",
    "egress_operation",
})


class AuditEventType(StrEnum):
    QUERY_RECEIVED = "query_received"
    RETRIEVAL_PERFORMED = "retrieval_performed"
    GENERATION_PERFORMED = "generation_performed"
    GUARD_DECISION = "guard_decision"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    EGRESS_DECISION = "egress_decision"  # Lot 20 (docs/refactoring-plan.md)


class AuditEvent(BaseModel):
    """One immutable, append-only compliance record.

    `correlation_id` ties every event from a single query/run together (the
    equivalent of `Trace.id` on the observability side, but kept as a plain
    field rather than a shared foreign key — audit storage must not depend
    on `core.models.trace` per the layering rule that domain modules share
    only `core/models/`, and audit is not itself a "domain module" import
    target). `causation_id` optionally points at the event that caused this
    one, for reconstructing a causal chain, not just a flat timeline.
    """

    schema_version: str = AUDIT_SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    event_type: AuditEventType
    correlation_id: str
    causation_id: str | None = None
    tenant_id: str
    actor: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)
    # ADR-0011 (PostgreSQL migrations, pooling, and retention): `retention_days` was
    # stored but never validated or enforced before this — a zero or negative value
    # would make `PostgresAuditSink.purge_expired()` treat the row as already/always
    # expired. Rejected at construction rather than only guarded defensively in the
    # purge query, so a caller gets an immediate, clear error instead of silently
    # scheduling a compliance record for immediate deletion.
    retention_days: int = Field(default=365, ge=1)

    @field_validator("payload")
    @classmethod
    def _enforce_payload_allowlist(cls, value: dict[str, Any]) -> dict[str, Any]:
        unexpected = set(value) - ALLOWED_PAYLOAD_KEYS
        if unexpected:
            raise ValueError(
                f"AuditEvent.payload contains non-allowlisted keys: {sorted(unexpected)}. "
                f"Allowed: {sorted(ALLOWED_PAYLOAD_KEYS)}"
            )
        return value


@runtime_checkable
class AuditSink(Protocol):
    """Persist AuditEvents. Append-only by contract: no update/delete method
    exists here on purpose. `security.audit.InMemoryAuditSink` is the
    reference implementation; `adapters.audit.postgres_sink.PostgresAuditSink`
    is the durable backend (Lot 10)."""

    def record(self, event: AuditEvent) -> None: ...

    async def arecord(self, event: AuditEvent) -> None: ...

    def name(self) -> str: ...
