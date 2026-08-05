"""Tests for contracts/reconciliation.py — DocumentDivergence,
ReconciliationReport, RepairResult. Lot 12b, docs/refactoring-plan.md.
"""
from __future__ import annotations

from modular_rag.contracts.reconciliation import DocumentDivergence, ReconciliationReport


def test_document_divergence_is_divergent_true_when_missing_entries_exist():
    d = DocumentDivergence(document_key="k1", missing_in_vector=["c1"])
    assert d.is_divergent is True


def test_document_divergence_is_divergent_false_when_nothing_missing():
    d = DocumentDivergence(document_key="k1")
    assert d.is_divergent is False


def test_reconciliation_report_is_clean_true_when_nothing_found():
    report = ReconciliationReport(documents_checked=3)
    assert report.is_clean is True


def test_reconciliation_report_is_clean_false_with_a_divergence():
    report = ReconciliationReport(
        documents_checked=1,
        divergences=[DocumentDivergence(document_key="k1", missing_in_vector=["c1"])],
    )
    assert report.is_clean is False


def test_reconciliation_report_is_clean_false_with_orphans():
    report = ReconciliationReport(documents_checked=1, orphaned_in_vector=["c9"])
    assert report.is_clean is False
