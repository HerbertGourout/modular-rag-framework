"""Helpers shared by the two suites that probe `ForeignApplicationAdapter`:
`test_application_behaviour.py` (profile claims) and
`test_engine_conformance.py` (the shared status-aware evidence harness).

Each helper reports an observable outcome; none of them asserts, so a negative
control can feed a deliberately broken adapter through the same code.
"""
from __future__ import annotations

from typing import Any

from modular_rag.contracts.assurance import EvidenceKind, EvidenceStatus, evidence_status_rank
from modular_rag.contracts.audit import AuditEventType
from modular_rag.contracts.engine import EngineRequest, ExecutionContext
from modular_rag.core.errors import PolicyViolationError, StorageError
from modular_rag.core.models.query import Query
from tests.contract.fakes.foreign_application import (
    TENANT_A,
    AuditLog,
    Controls,
    ForeignApplicationAdapter,
)


def context(tenant: str | None = TENANT_A, request_id: str = "req-1") -> ExecutionContext:
    return ExecutionContext(tenant_id=tenant, correlation_id="corr-1", request_id=request_id)


def request(text: str = "what is the policy?", tenant_id: str | None = None) -> EngineRequest:
    return EngineRequest(query=Query(text=text, tenant_id=tenant_id))


def open_result(**overrides: Any) -> Controls:
    """Controls that let a result through, so a probe isolates one effect. A
    tenant-blind application would otherwise be (correctly) withheld, which is
    the two-tenant probe's subject, not this one's."""
    return Controls(admit_result=lambda *_: True, **overrides)


def serves(adapter: ForeignApplicationAdapter, tenant: str = TENANT_A) -> bool:
    try:
        adapter.run(request(), context(tenant))
    except Exception:
        return False
    return True


def is_denied(adapter: ForeignApplicationAdapter, tenant: str = TENANT_A) -> bool:
    try:
        adapter.run(request(), context(tenant))
    except PolicyViolationError:
        return True
    except Exception:
        return False
    return False


async def stream_texts(adapter: ForeignApplicationAdapter) -> list[str] | None:
    """The fragments a caller received, or `None` when the stream was refused."""
    try:
        return [step.metadata["text"] async for step in adapter.astream(request(), context())]
    except PolicyViolationError:
        return None


def lost_terminal_event_is_surfaced(make: Any) -> bool:
    """A failed run whose `RUN_FAILED` cannot be persisted must say so to the
    caller and must not be reported as audit-complete."""
    adapter = make(
        controls=open_result(admit_request=lambda *_: False),
        audit=AuditLog(fail_on=frozenset({AuditEventType.RUN_FAILED})),
    )
    try:
        adapter.run(request(), context())
    except StorageError:
        pass
    except Exception:
        return False
    else:
        return False
    status = adapter.conformance_report(context()).evidence_for(EvidenceKind.AUDIT_COMPLETION)
    return evidence_status_rank(status.status) < evidence_status_rank(EvidenceStatus.ENFORCED)
