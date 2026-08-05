"""Tests for contracts/identity.py — TenantContext, TokenVerifier. Lot 11b,
docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.identity import TenantContext, TokenVerifier


def test_tenant_context_defaults_empty_roles():
    ctx = TenantContext(tenant_id="acme-corp", user_id="user-1")
    assert ctx.roles == frozenset()


def test_tenant_context_is_frozen():
    ctx = TenantContext(tenant_id="acme-corp", user_id="user-1")
    try:
        ctx.tenant_id = "other"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised


class _FakeTokenVerifier:
    def verify(self, token: str) -> TenantContext:
        return TenantContext(tenant_id="acme-corp", user_id="user-1")

    def name(self) -> str:
        return "fake"


def test_fake_verifier_satisfies_the_protocol():
    assert isinstance(_FakeTokenVerifier(), TokenVerifier)
