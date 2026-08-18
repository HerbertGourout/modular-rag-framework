"""Health-check port (Lot 6 — readiness and resilience).

A minimal, opt-in capability: any component that owns a connection to an
external service (Qdrant, PostgreSQL) can implement this to be probed by
`orchestration.container.Container.check_readiness()`. Not every component
implements it — an in-memory store (`BM25Retriever`, `InMemoryAuditSink`,
`InMemoryLifecycleLedger`) has nothing external to check, and `Container`
discovers this Protocol the same way it already discovers `close()`:
`hasattr(component, "check_health")`, not `isinstance()` — `orchestration/`
may only import `core/` + `contracts/` + `orchestration/` (never concrete
adapters), so duck-typing is the only way it can reach into whichever
adapter a manifest actually wired.

Returns `list[DependencyHealth]`, not one — a wrapping component (e.g.
`retrieval.retrievers.hybrid.HybridRetriever`) may need to report on more
than one leg, or on none if its leg has nothing external to check.

See [ADR-0010](../../../docs/adr/0010-health-checkable-and-readiness-semantics.md)
for the full port boundary, three-state readiness semantics, probe
budget/side-effect constraints, and compatibility rules a future
implementation must follow.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.health import DependencyHealth


@runtime_checkable
class HealthCheckable(Protocol):
    def check_health(self) -> list[DependencyHealth]: ...
