"""Unit tests for security/policies/tenant_isolation.py — TenantIsolationPolicy.
Lot 11b, docs/refactoring-plan.md.
"""
from __future__ import annotations

import pytest

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import PolicyViolationError
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.security.policies.tenant_isolation import TenantIsolationPolicy


def _hit(tenant_id: str | None) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content="hit", tenant_id=tenant_id)
    return RetrievedChunk(chunk=chunk, score=0.5, rank=1, retrieval_method=RetrievalMethod.HYBRID)


def test_enforce_query_denies_missing_tenant_id():
    policy = TenantIsolationPolicy()

    with pytest.raises(PolicyViolationError, match="tenant_id"):
        policy.enforce_query(Query(text="hello"))


def test_enforce_query_denies_empty_string_tenant_id():
    policy = TenantIsolationPolicy()

    with pytest.raises(PolicyViolationError):
        policy.enforce_query(Query(text="hello", tenant_id=""))


def test_enforce_query_allows_a_populated_tenant_id():
    TenantIsolationPolicy().enforce_query(Query(text="hello", tenant_id="acme-corp"))


def test_enforce_ingest_denies_missing_tenant_id():
    with pytest.raises(PolicyViolationError, match="tenant_id"):
        TenantIsolationPolicy().enforce_ingest(None)


def test_enforce_ingest_denies_empty_string_tenant_id():
    """Symmetric with enforce_query's equivalent test — an empty string is
    the one falsy value `str | None` still permits through, not caught by
    an `is None` check alone."""
    with pytest.raises(PolicyViolationError, match="tenant_id"):
        TenantIsolationPolicy().enforce_ingest("")


def test_enforce_ingest_allows_a_populated_tenant_id():
    TenantIsolationPolicy().enforce_ingest("acme-corp")


def test_filter_chunks_excludes_other_tenants():
    policy = TenantIsolationPolicy()
    chunks = [_hit("acme-corp"), _hit("other-tenant")]

    result = policy.filter_chunks("acme-corp", chunks)

    assert len(result) == 1
    assert result[0].chunk.tenant_id == "acme-corp"


def test_filter_chunks_excludes_chunks_with_no_tenant_id():
    """Fail-closed: an unclassified/legacy chunk is not treated as implicitly
    accessible to every tenant."""
    policy = TenantIsolationPolicy()
    chunks = [_hit(None)]

    result = policy.filter_chunks("acme-corp", chunks)

    assert result == []


def test_filter_chunks_on_empty_input_returns_empty():
    assert TenantIsolationPolicy().filter_chunks("acme-corp", []) == []


def test_name_reports_tenant_isolation():
    assert TenantIsolationPolicy().name() == "tenant-isolation"
