from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query


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
