"""Tests for contracts/review.py — ReviewItem defaults. Lot 11c,
docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.review import ReviewItem


def test_review_item_defaults():
    item = ReviewItem(answer_id="a1", query_id="q1", reason="low confidence")
    assert item.id
    assert item.resolved is False
    assert item.approved is None
    assert item.reviewer is None
    assert item.tenant_id is None
    # ADR-0014 (Batch 14): purely additive, same default as
    # AuditEvent.retention_days (ADR-0011).
    assert item.retention_days == 365
