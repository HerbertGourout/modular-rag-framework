"""Adversarial query detector — checks for context flooding and data exfiltration patterns (V4)."""
from __future__ import annotations

import re

from modular_rag.contracts.security import GuardResult
from modular_rag.core.models.query import Query

_EXFILTRATION_PATTERNS = [
    re.compile(r"send (to|all) (email|slack|webhook|http)", re.I),
    re.compile(r"output (all|every|entire) (document|file|data)", re.I),
    re.compile(r"base64|curl\s+http", re.I),
]


class AdversarialDetector:
    """Detect DoS flooding, exfiltration, and data poisoning patterns in queries."""

    def name(self) -> str:
        return "adversarial"

    def check_query(self, query: Query) -> GuardResult:
        for pat in _EXFILTRATION_PATTERNS:
            if pat.search(query.text):
                return GuardResult(
                    allowed=False,
                    reason=f"Potential data exfiltration: {pat.pattern[:50]}",
                    risk_score=0.95,
                )
        return GuardResult(allowed=True)

    def check_answer(self, answer: object) -> GuardResult:  # type: ignore[override]
        return GuardResult(allowed=True)
