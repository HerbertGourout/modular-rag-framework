"""Contract conformance tests for SecurityGuard, Redactor, and TenantPolicy
implementations."""
from __future__ import annotations

import pytest

from modular_rag.contracts.security import GuardResult, Redactor, SecurityGuard, TenantPolicy
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.security.filters.basic_guard import BasicSecurityGuard
from modular_rag.security.policies.tenant_isolation import TenantIsolationPolicy
from modular_rag.security.redaction.patterns import PatternRedactor

GUARDS = [BasicSecurityGuard()]
REDACTORS = [PatternRedactor()]
TENANT_POLICIES = [TenantIsolationPolicy()]


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_implements_security_guard_protocol(guard):
    assert isinstance(guard, SecurityGuard)


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_check_query_returns_guard_result(guard):
    q = Query(text="What is the weather today?")
    result = guard.check_query(q)
    assert isinstance(result, GuardResult)
    assert isinstance(result.allowed, bool)
    assert isinstance(result.reason, str)
    assert 0.0 <= result.risk_score <= 1.0


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_check_answer_returns_guard_result(guard):
    a = Answer(query_id=new_id(), text="The answer is 42.")
    result = guard.check_answer(a)
    assert isinstance(result, GuardResult)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_implements_redactor_protocol(redactor):
    assert isinstance(redactor, Redactor)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_redact_returns_string(redactor):
    result = redactor.redact("Hello world")
    assert isinstance(result, str)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_redact_benign_text_unchanged(redactor):
    text = "The quick brown fox jumps over the lazy dog."
    assert redactor.redact(text) == text


def _chunk(tenant_id: str | None) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content="hit", tenant_id=tenant_id)
    return RetrievedChunk(chunk=chunk, score=0.5, rank=1, retrieval_method=RetrievalMethod.HYBRID)


@pytest.mark.parametrize("policy", TENANT_POLICIES, ids=lambda p: p.name())
def test_implements_tenant_policy_protocol(policy):
    assert isinstance(policy, TenantPolicy)


@pytest.mark.parametrize("policy", TENANT_POLICIES, ids=lambda p: p.name())
def test_enforce_query_denies_a_query_with_no_tenant_id(policy):
    with pytest.raises(PolicyViolationError):
        policy.enforce_query(Query(text="hello"))


@pytest.mark.parametrize("policy", TENANT_POLICIES, ids=lambda p: p.name())
def test_enforce_query_allows_a_query_with_a_tenant_id(policy):
    policy.enforce_query(Query(text="hello", tenant_id="acme-corp"))  # must not raise


@pytest.mark.parametrize("policy", TENANT_POLICIES, ids=lambda p: p.name())
def test_enforce_ingest_denies_missing_tenant_id(policy):
    with pytest.raises(PolicyViolationError):
        policy.enforce_ingest(None)


@pytest.mark.parametrize("policy", TENANT_POLICIES, ids=lambda p: p.name())
def test_filter_chunks_keeps_only_matching_tenant(policy):
    chunks = [_chunk("acme-corp"), _chunk("other-tenant"), _chunk(None)]

    result = policy.filter_chunks("acme-corp", chunks)

    assert len(result) == 1
    assert result[0].chunk.tenant_id == "acme-corp"
