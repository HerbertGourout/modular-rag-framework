from __future__ import annotations

import re

from modular_rag.contracts.security import GuardResult
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (your|the) (system|previous) (prompt|instructions)", re.I),
    re.compile(r"you are now|pretend (you are|to be)", re.I),
    re.compile(r"jailbreak|DAN mode|act as DAN|bypass all restrictions", re.I),
    re.compile(r"<!--\s*ignore|<\s*script\s*>|javascript:", re.I),
]

_BLOCKED_TERMS = frozenset(["rm -rf", "os.system", "exec(", "__import__"])


class BasicSecurityGuard:
    """First-line defence: detect prompt injection and obvious blocked content."""

    def __init__(self, max_query_length: int = 4000) -> None:
        self.max_query_length = max_query_length

    def name(self) -> str:
        return "basic-security-guard"

    def check_query(self, query: Query) -> GuardResult:
        text = query.text

        if len(text) > self.max_query_length:
            return GuardResult(allowed=False, reason="Query exceeds maximum length.", risk_score=0.5)

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return GuardResult(
                    allowed=False,
                    reason=f"Potential prompt injection detected: {pattern.pattern[:40]}",
                    risk_score=0.9,
                )

        for term in _BLOCKED_TERMS:
            if term in text:
                return GuardResult(allowed=False, reason=f"Blocked term detected: {term}", risk_score=0.8)

        return GuardResult(allowed=True, reason="", risk_score=0.0)

    def check_answer(self, answer: Answer) -> GuardResult:
        return GuardResult(allowed=True, reason="", risk_score=0.0)
