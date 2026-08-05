from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


@dataclass
class GuardResult:
    allowed: bool
    reason: str | None = None
    modified_content: str | None = None
    risk_score: float = 0.0


@runtime_checkable
class SecurityGuard(Protocol):
    """Inspect queries, contexts, and answers for policy violations."""

    def check_query(self, query: Query) -> GuardResult: ...

    def check_answer(self, answer: Answer) -> GuardResult: ...

    def name(self) -> str: ...


@runtime_checkable
class Redactor(Protocol):
    """Remove or mask sensitive patterns from text (V4)."""

    def redact(self, text: str) -> str: ...

    def name(self) -> str: ...


@runtime_checkable
class TenantPolicy(Protocol):
    """Fail-closed tenant-isolation boundary (Lot 11b, docs/refactoring-plan.md).
    `security.policies.tenant_isolation.TenantIsolationPolicy` is the reference
    implementation; registered on `Container.tenant_policy` — optional, mirrors
    `SecurityGuard`'s optionality."""

    def enforce_query(self, query: Query) -> None: ...

    def enforce_ingest(self, tenant_id: str | None) -> None: ...

    def filter_chunks(
        self, tenant_id: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]: ...

    def name(self) -> str: ...
