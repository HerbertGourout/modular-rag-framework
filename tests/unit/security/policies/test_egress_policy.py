"""Unit tests for security/policies/egress_policy.py — ManifestEgressPolicy.
Lot 20, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.egress import EgressOperation
from modular_rag.core.enums import DataClassification
from modular_rag.core.errors import ConfigurationError
from modular_rag.security.policies.egress_policy import ManifestEgressPolicy


def test_local_provider_always_allowed_regardless_of_classification():
    policy = ManifestEgressPolicy(providers={"sentence-transformers": {"local": True}})

    decision = policy.check(
        classification=DataClassification.RESTRICTED,
        provider="sentence-transformers",
        operation=EgressOperation.EMBED,
    )

    assert decision.allowed is True


def test_local_provider_allowed_even_when_unclassified():
    policy = ManifestEgressPolicy(providers={"sentence-transformers": {"local": True}})

    decision = policy.check(
        classification=None, provider="sentence-transformers", operation=EgressOperation.EMBED
    )

    assert decision.allowed is True


def test_remote_provider_allows_classification_at_or_under_its_ceiling():
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "confidential"}}
    )

    for level in (
        DataClassification.PUBLIC,
        DataClassification.INTERNAL,
        DataClassification.CONFIDENTIAL,
    ):
        decision = policy.check(
            classification=level, provider="openai", operation=EgressOperation.GENERATE
        )
        assert decision.allowed is True, level


def test_remote_provider_denies_classification_over_its_ceiling():
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "confidential"}}
    )

    decision = policy.check(
        classification=DataClassification.RESTRICTED,
        provider="openai",
        operation=EgressOperation.GENERATE,
    )

    assert decision.allowed is False
    assert "restricted" in decision.reason
    assert decision.provider == "openai"
    assert decision.operation is EgressOperation.GENERATE


def test_unknown_provider_is_denied_not_silently_allowed():
    """Fail-closed: a provider with no configured profile at all must never
    default to allowed."""
    policy = ManifestEgressPolicy(providers={"sentence-transformers": {"local": True}})

    decision = policy.check(
        classification=DataClassification.PUBLIC,
        provider="some-unconfigured-provider",
        operation=EgressOperation.GENERATE,
    )

    assert decision.allowed is False
    assert "some-unconfigured-provider" in decision.reason


def test_unclassified_content_uses_the_default_classification():
    """Unknown classification is denied by default (acceptance criterion):
    an unclassified chunk against a provider whose ceiling is below the
    configured default_classification is denied."""
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "internal"}},
        default_classification="restricted",
    )

    decision = policy.check(classification=None, provider="openai", operation=EgressOperation.EMBED)

    assert decision.allowed is False


def test_unclassified_content_allowed_when_default_classification_is_permissive():
    """An operator may explicitly opt an unclassified default in — this is a
    deliberate manifest configuration choice, not the framework's own
    default (the constructor's own default_classification is "restricted")."""
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "internal"}},
        default_classification="public",
    )

    decision = policy.check(classification=None, provider="openai", operation=EgressOperation.EMBED)

    assert decision.allowed is True


def test_default_classification_defaults_to_restricted():
    """The framework's own default, not just an operator convention (fail
    closed by default, per data-classification-policy.md's own
    recommendation)."""
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "confidential"}}
    )

    decision = policy.check(
        classification=None, provider="openai", operation=EgressOperation.GENERATE
    )

    assert decision.allowed is False


def test_non_local_provider_without_max_classification_is_rejected_at_construction():
    """Fail loud at wiring time, not silently at the first request."""
    with pytest.raises(ConfigurationError, match="max_classification"):
        ManifestEgressPolicy(providers={"openai": {"local": False}})


def test_invalid_max_classification_value_is_rejected_at_construction():
    with pytest.raises(ConfigurationError, match="DataClassification"):
        ManifestEgressPolicy(
            providers={"openai": {"local": False, "max_classification": "top-secret"}}
        )


def test_invalid_default_classification_value_is_rejected_at_construction():
    with pytest.raises(ConfigurationError, match="DataClassification"):
        ManifestEgressPolicy(default_classification="not-a-real-level")


def test_no_providers_configured_denies_everything():
    policy = ManifestEgressPolicy()

    decision = policy.check(
        classification=DataClassification.PUBLIC,
        provider="openai",
        operation=EgressOperation.GENERATE,
    )

    assert decision.allowed is False


def test_known_providers_reports_configured_provider_keys():
    policy = ManifestEgressPolicy(
        providers={
            "sentence-transformers": {"local": True},
            "openai": {"local": False, "max_classification": "confidential"},
        }
    )

    assert policy.known_providers == frozenset({"sentence-transformers", "openai"})


def test_decision_never_carries_the_classified_content_itself():
    """EgressDecision is meant to be safe to audit/log verbatim — a
    structural guard that the dataclass has no free-text field beyond the
    bounded reason string built from classification/provider/operation
    names, never caller-supplied content."""
    policy = ManifestEgressPolicy(
        providers={"openai": {"local": False, "max_classification": "public"}}
    )

    decision = policy.check(
        classification=DataClassification.RESTRICTED,
        provider="openai",
        operation=EgressOperation.GENERATE,
    )

    assert set(decision.__dataclass_fields__) == {
        "allowed",
        "reason",
        "classification",
        "provider",
        "operation",
    }


def test_name_reports_manifest():
    assert ManifestEgressPolicy().name() == "manifest"
