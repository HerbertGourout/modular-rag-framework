"""Dependency-health and pipeline-readiness models (Lot 6 — readiness and
resilience). Kept separate from `core/models/trace.py`: a `TraceStep` records
what happened during one query's execution; `DependencyHealth`/
`ReadinessReport` record the current, point-in-time reachability of the
external services a wired pipeline depends on — read by `/ready`, not by
per-request tracing.

See [ADR-0010](../../../../docs/adr/0010-health-checkable-and-readiness-semantics.md)
for the full readiness-semantics decision record.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from modular_rag.core.enums import ReadinessState


class DependencyHealth(BaseModel):
    """Result of one `contracts.health.HealthCheckable.check_health()` probe.

    `role` is filled in by `orchestration.container.Container.check_readiness()`,
    not by the probing adapter itself — an adapter (e.g. `PostgresAuditSink`)
    has no idea which manifest role it was wired under, only its own `name()`.
    Without it, two dependencies sharing one `name()` (both Postgres adapters
    report `"postgres"`) are indistinguishable in a `/ready` payload even
    though only one of them may be critical (orchestration-specialist review,
    Lot 6).
    """

    name: str
    healthy: bool
    detail: str | None = None
    latency_ms: float = 0.0
    role: str | None = None


class ReadinessReport(BaseModel):
    """Aggregate result of `orchestration.container.Container.check_readiness()`.

    `status` is derived from `dependencies`, not stored redundantly by the
    caller — see `Container.check_readiness()`'s own docstring for exactly
    which roles are treated as critical (→ `UNREADY`) vs. not (→ `DEGRADED`).
    """

    status: ReadinessState
    dependencies: list[DependencyHealth] = Field(default_factory=list)
