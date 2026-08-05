"""Policy-as-code enforcement engine (V4)."""
from __future__ import annotations

import structlog

from modular_rag.contracts.security import GuardResult
from modular_rag.core.enums import PolicyAction
from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.models.policy import Policy
from modular_rag.core.models.query import Query

log = structlog.get_logger(__name__)


class PolicyEngine:
    """Evaluate a set of Policies against a Query or Answer at runtime."""

    def __init__(self, policies: list[Policy]) -> None:
        self._policies = [p for p in policies if p.enabled]

    def enforce_query(self, query: Query) -> GuardResult:
        for policy in self._policies:
            for rule in policy.sorted_rules():
                try:
                    matched = self._evaluate(rule.condition, query.text)
                except Exception as exc:
                    # Lot 11b (docs/refactoring-plan.md): "policy-engine errors deny
                    # by default, never allow by default." A rule that fails to
                    # evaluate (a future CEL/Rego condition parse error, e.g.) must
                    # not be silently skipped as non-matching — that would let the
                    # query through exactly when the engine is least sure about it.
                    log.error("policy.evaluation_failed", rule=rule.name, error=str(exc))
                    raise PolicyViolationError(
                        f"Rule '{rule.name}' failed to evaluate — denied by default "
                        f"(fail-closed)."
                    ) from exc
                if matched:
                    if rule.action == PolicyAction.DENY:
                        raise PolicyViolationError(f"Rule '{rule.name}' denied the query.")
                    if rule.action == PolicyAction.WARN:
                        log.warning("policy.warn", rule=rule.name, query_id=query.id)
        return GuardResult(allowed=True)

    def _evaluate(self, condition: str, text: str) -> bool:
        """Evaluate a simple keyword condition (extensible to CEL or Rego in V4)."""
        return condition.lower() in text.lower()
