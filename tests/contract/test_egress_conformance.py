"""Semantic conformance tests for the EgressPolicy port (contracts/egress.py,
Lot 20, docs/refactoring-plan.md). Parametrized over every registered
implementation — currently only `ManifestEgressPolicy`.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.egress import EgressDecision, EgressOperation, EgressPolicy
from modular_rag.core.enums import DataClassification
from modular_rag.security.policies.egress_policy import ManifestEgressPolicy

POLICY_FACTORIES = [
    lambda: ManifestEgressPolicy(
        providers={
            "sentence-transformers": {"local": True},
            "openai": {"local": False, "max_classification": "confidential"},
        }
    )
]


@pytest.mark.parametrize("policy_factory", POLICY_FACTORIES)
def test_policy_satisfies_the_protocol(policy_factory) -> None:
    assert isinstance(policy_factory(), EgressPolicy)


@pytest.mark.parametrize("policy_factory", POLICY_FACTORIES)
def test_check_returns_an_egress_decision(policy_factory) -> None:
    policy = policy_factory()

    decision = policy.check(
        classification=DataClassification.PUBLIC,
        provider="sentence-transformers",
        operation=EgressOperation.EMBED,
    )

    assert isinstance(decision, EgressDecision)
    assert isinstance(decision.allowed, bool)
    assert isinstance(decision.reason, str) and decision.reason
    assert decision.provider == "sentence-transformers"
    assert decision.operation is EgressOperation.EMBED


@pytest.mark.parametrize("policy_factory", POLICY_FACTORIES)
def test_local_provider_is_always_allowed(policy_factory) -> None:
    """Cross-implementation invariant, not just ManifestEgressPolicy's own
    behavior: preserving the local/offline fallback is part of the
    contract's own intent (see EgressPolicy's docstring), not an
    implementation detail of one reference class."""
    policy = policy_factory()

    decision = policy.check(
        classification=DataClassification.RESTRICTED,
        provider="sentence-transformers",
        operation=EgressOperation.EMBED,
    )

    assert decision.allowed is True


@pytest.mark.parametrize("policy_factory", POLICY_FACTORIES)
def test_unknown_provider_is_denied(policy_factory) -> None:
    """Fail-closed cross-implementation invariant: a provider with no
    profile must never default to allowed."""
    policy = policy_factory()

    decision = policy.check(
        classification=DataClassification.PUBLIC,
        provider="an-unconfigured-provider",
        operation=EgressOperation.GENERATE,
    )

    assert decision.allowed is False


@pytest.mark.parametrize("policy_factory", POLICY_FACTORIES)
def test_policy_has_a_name(policy_factory) -> None:
    assert policy_factory().name()
