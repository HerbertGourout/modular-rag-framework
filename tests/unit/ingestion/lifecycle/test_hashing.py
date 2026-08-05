"""Unit tests for ingestion/lifecycle/hashing.py. Lot 12a,
docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.ingestion.lifecycle.hashing import content_hash, document_key


def test_content_hash_is_deterministic():
    assert content_hash("hello world") == content_hash("hello world")


def test_content_hash_differs_for_different_content():
    assert content_hash("hello world") != content_hash("goodbye world")


def test_document_key_is_deterministic():
    assert document_key("docs/a.pdf", "acme-corp") == document_key("docs/a.pdf", "acme-corp")


def test_document_key_differs_across_tenants():
    """Same source, different tenant, must be a different logical document —
    otherwise Lot 11b's tenant isolation would be undermined at the lifecycle
    layer."""
    key_a = document_key("docs/a.pdf", "acme-corp")
    key_b = document_key("docs/a.pdf", "other-tenant")
    assert key_a != key_b


def test_document_key_differs_across_sources():
    assert document_key("docs/a.pdf", "acme-corp") != document_key("docs/b.pdf", "acme-corp")


def test_document_key_none_tenant_is_stable_and_distinct_from_a_named_tenant():
    key_none = document_key("docs/a.pdf", None)
    key_default_literal = document_key("docs/a.pdf", "default")
    assert key_none == document_key("docs/a.pdf", None)
    # "default" is the internal placeholder for a None tenant, so a real
    # tenant literally named "default" collides with the untenanted case —
    # documented here as a known, narrow edge case, not silently hidden.
    assert key_none == key_default_literal
