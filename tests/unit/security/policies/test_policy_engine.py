"""Unit tests for security/policies/policy_engine.py — PolicyEngine, including
the Lot 11b fail-closed fix (docs/refactoring-plan.md: "policy-engine errors
deny by default, never allow by default").
"""
from __future__ import annotations

import pytest

from modular_rag.core.enums import PolicyAction
from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.models.policy import Policy, PolicyRule
from modular_rag.core.models.query import Query
from modular_rag.security.policies.policy_engine import PolicyEngine


def _policy(action: PolicyAction, condition: str = "forbidden") -> Policy:
    rule = PolicyRule(name="r1", condition=condition, action=action)
    return Policy(name="test-policy", rules=[rule])


def test_enforce_query_allows_when_no_rule_matches():
    engine = PolicyEngine([_policy(PolicyAction.DENY)])

    result = engine.enforce_query(Query(text="a benign question"))

    assert result.allowed is True


def test_enforce_query_denies_when_a_deny_rule_matches():
    engine = PolicyEngine([_policy(PolicyAction.DENY)])

    with pytest.raises(PolicyViolationError, match="r1"):
        engine.enforce_query(Query(text="this is forbidden content"))


def test_enforce_query_warns_but_allows_when_a_warn_rule_matches():
    engine = PolicyEngine([_policy(PolicyAction.WARN)])

    result = engine.enforce_query(Query(text="this is forbidden content"))

    assert result.allowed is True


def test_disabled_policies_are_never_evaluated():
    policy = _policy(PolicyAction.DENY)
    policy.enabled = False
    engine = PolicyEngine([policy])

    result = engine.enforce_query(Query(text="this is forbidden content"))

    assert result.allowed is True


class _RaisingPolicyEngine(PolicyEngine):
    """Forces `_evaluate` to fail, to exercise the fail-closed path — a
    genuine defensive-code test, not a shortcut around business logic that
    could be tested directly (`_evaluate`'s current implementation is a
    trivial substring match that can't itself raise on any Policy/Query
    input; the failure mode under test is what happens to *callers* when a
    future evaluator — CEL/Rego — does raise)."""

    def _evaluate(self, condition: str, text: str) -> bool:
        raise RuntimeError("simulated policy-evaluation engine failure")


def test_enforce_query_denies_by_default_when_evaluation_raises():
    """The core Lot 11b regression test: an evaluation failure must deny,
    never silently pass the query through as allowed."""
    engine = _RaisingPolicyEngine([_policy(PolicyAction.DENY)])

    with pytest.raises(PolicyViolationError, match="failed to evaluate"):
        engine.enforce_query(Query(text="anything"))
