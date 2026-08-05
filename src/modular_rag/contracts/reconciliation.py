"""Index-reconciliation report shapes (Lot 12b, docs/refactoring-plan.md —
"implement the reconciliation job that detects and repairs BM25/vector
divergence").

No Protocol here, deliberately: unlike `AuditSink`/`LifecycleLedger` (where
multiple backend implementations make sense — in-memory vs. PostgreSQL),
reconciliation is a single orchestration-level job that operates *on*
already-Protocol'd components (`Indexer`, the retriever's duck-typed
`list_ids()`, `LifecycleLedger`) — see
`orchestration.reconciliation.IndexReconciler`, which is a concrete class,
not a swappable adapter target.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class DocumentDivergence(BaseModel):
    """One document whose ledger-expected chunk ids don't match what's
    actually present in the vector index and/or the lexical retriever."""

    document_key: str
    missing_in_vector: list[str] = Field(default_factory=list)
    missing_in_lexical: list[str] = Field(default_factory=list)

    @property
    def is_divergent(self) -> bool:
        return bool(self.missing_in_vector or self.missing_in_lexical)


class ReconciliationReport(BaseModel):
    """Result of `IndexReconciler.check()`. `orphaned_in_vector`/
    `orphaned_in_lexical` are ids present in a store but not expected by
    *any* active ledger record — candidates for cleanup, not tied to one
    document. `divergences` covers the opposite direction: a specific
    document's expected chunks missing from one or both stores.
    """

    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    documents_checked: int = 0
    divergences: list[DocumentDivergence] = Field(default_factory=list)
    orphaned_in_vector: list[str] = Field(default_factory=list)
    orphaned_in_lexical: list[str] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (
            self.divergences or self.orphaned_in_vector or self.orphaned_in_lexical
        )


class RepairResult(BaseModel):
    """Result of `IndexReconciler.repair()`. Only orphans are actually
    repairable automatically (pure deletion — no content regeneration
    needed). `unresolved_missing` lists documents whose missing chunks
    could not be repaired here, because there is no chunk *content* stored
    in the ledger to re-index from — only ids. Regenerating those requires
    the original source content, which is Lot 12c's "rebuild-from-source"
    scope, not this job's: fabricating placeholder embeddings/BM25 entries
    to silence the divergence would be actively wrong.
    """

    removed_orphans_in_vector: list[str] = Field(default_factory=list)
    removed_orphans_in_lexical: list[str] = Field(default_factory=list)
    unresolved_missing: list[DocumentDivergence] = Field(default_factory=list)
