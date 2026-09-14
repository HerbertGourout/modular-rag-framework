"""Integration tests for OpaEgressPolicy — requires OPA on localhost:8181
serving tests/integration/fixtures/opa/egress.rego.

CI starts it in the `test-integration` job. Locally:

    docker run --rm -p 8181:8181 \
      -v "$PWD/tests/integration/fixtures/opa:/policies:ro" \
      openpolicyagent/opa:1.20.2 run --server --addr=0.0.0.0:8181 /policies

The fixture policy allows `openai` for `public`/`internal` content only and
denies everything else by default.
"""
import pytest

from modular_rag.adapters.policy.opa_egress_policy import OpaEgressPolicy
from modular_rag.contracts.egress import EgressOperation
from modular_rag.core.enums import DataClassification

OPA_URL = "http://localhost:8181"
PROVIDERS = {"sentence-transformers": {"local": True}, "openai": {"local": False}}


def _policy(**overrides):
    # Caching off: each test must observe a real round-trip to OPA.
    config = {"url": OPA_URL, "providers": PROVIDERS, "cache_ttl_seconds": 0}
    config.update(overrides)
    return OpaEgressPolicy(**config)


def _check(policy, classification):
    return policy.check(
        classification=classification, provider="openai", operation=EgressOperation.GENERATE
    )


@pytest.mark.integration
def test_real_opa_allows_what_the_policy_allows():
    assert _check(_policy(), DataClassification.INTERNAL).allowed is True


@pytest.mark.integration
def test_real_opa_denies_what_the_policy_denies():
    decision = _check(_policy(), DataClassification.CONFIDENTIAL)

    assert decision.allowed is False
    assert "denied" in decision.reason


@pytest.mark.integration
def test_unclassified_content_is_judged_at_the_default_classification():
    assert _check(_policy(), None).allowed is False  # default: restricted
    assert _check(_policy(default_classification="public"), None).allowed is True


@pytest.mark.integration
def test_an_undefined_decision_path_denies():
    """OPA answers `{}` for a document no rule defines. That must deny, never
    be read as an allow."""
    decision = _check(
        _policy(decision_path="modular_rag/egress/does_not_exist"), DataClassification.PUBLIC
    )

    assert decision.allowed is False
    assert "no decision" in decision.reason


@pytest.mark.integration
def test_health_is_healthy_against_a_real_opa():
    [health] = _policy().check_health()

    assert health.healthy is True


@pytest.mark.integration
def test_an_unreachable_opa_denies_and_reports_unhealthy():
    policy = _policy(url="http://localhost:1", timeout_seconds=0.5)

    assert _check(policy, DataClassification.PUBLIC).allowed is False
    [health] = policy.check_health()
    assert health.healthy is False
