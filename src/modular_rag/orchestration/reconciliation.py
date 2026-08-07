"""Index reconciliation (Lot 12b, docs/refactoring-plan.md — "implement the
reconciliation job that detects and repairs BM25/vector divergence").

`RAGEngine` already coordinates deletion across the vector index and the
lexical retriever (Lot 12a's `_delete_chunk_ids`), but nothing detects
divergence that happens *outside* that coordinated path — a caller bypassing
`RAGEngine` and calling `Container.indexer.delete()` directly, a process
crash between the two writes `ingest_chunks()` performs, or a store restored
from an out-of-sync backup. `IndexReconciler` treats the `LifecycleLedger`'s
`chunk_ids` as ground truth for what *should* be indexed, and compares it
against what each store actually reports having.
"""
from __future__ import annotations

from modular_rag.contracts.reconciliation import (
    DocumentDivergence,
    ReconciliationReport,
    RepairResult,
)
from modular_rag.core.errors import ConfigurationError
from modular_rag.orchestration.container import Container


class IndexReconciler:
    """Operates on an already-wired `Container` — not itself a swappable
    backend (see `contracts/reconciliation.py`'s module docstring for why
    there's no Protocol here)."""

    def __init__(self, container: Container) -> None:
        self._c = container

    def check(self) -> ReconciliationReport:
        """Detect divergence. Requires a configured `lifecycle_ledger` — the
        ledger's `chunk_ids` per active document is the only source of truth
        this job has for "what should be indexed"; without one there is
        nothing to reconcile against."""
        ledger = self._c.lifecycle_ledger
        if ledger is None:
            raise ConfigurationError(
                "IndexReconciler requires a configured Container.lifecycle_ledger."
            )
        active_records = ledger.list_active()
        vector_ids = set(self._c.indexer.list_ids())
        lexical_ids = set(self._list_lexical_ids())

        all_expected: set[str] = set()
        divergences: list[DocumentDivergence] = []
        for record in active_records:
            expected = set(record.chunk_ids)
            all_expected |= expected
            missing_in_vector = sorted(expected - vector_ids)
            missing_in_lexical = sorted(expected - lexical_ids)
            if missing_in_vector or missing_in_lexical:
                divergences.append(
                    DocumentDivergence(
                        document_key=record.document_key,
                        missing_in_vector=missing_in_vector,
                        missing_in_lexical=missing_in_lexical,
                    )
                )

        return ReconciliationReport(
            documents_checked=len(active_records),
            divergences=divergences,
            orphaned_in_vector=sorted(vector_ids - all_expected),
            orphaned_in_lexical=sorted(lexical_ids - all_expected),
        )

    def repair(self, report: ReconciliationReport) -> RepairResult:
        """Repair what's safely repairable: orphaned ids (present in a store,
        expected by no active document) are deleted outright — pure cleanup,
        no content regeneration needed. Missing ids are *not* auto-repaired
        here (see `contracts.reconciliation.RepairResult`'s docstring for
        why) — they're returned as `unresolved_missing` for Lot 12c's
        rebuild-from-source to address.
        """
        removed_vector: list[str] = []
        if report.orphaned_in_vector:
            self._c.indexer.delete(report.orphaned_in_vector)
            removed_vector = list(report.orphaned_in_vector)

        removed_lexical: list[str] = []
        if report.orphaned_in_lexical:
            retriever = self._c.retriever
            if hasattr(retriever, "delete"):
                retriever.delete(report.orphaned_in_lexical)
                removed_lexical = list(report.orphaned_in_lexical)

        return RepairResult(
            removed_orphans_in_vector=removed_vector,
            removed_orphans_in_lexical=removed_lexical,
            unresolved_missing=list(report.divergences),
        )

    def _list_lexical_ids(self) -> list[str]:
        retriever = self._c.retriever
        if hasattr(retriever, "list_ids"):
            return retriever.list_ids()  # type: ignore[no-any-return]
        return []
