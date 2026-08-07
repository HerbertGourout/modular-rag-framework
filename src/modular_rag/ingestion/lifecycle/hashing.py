"""Document-identity helpers (Lot 12a, docs/refactoring-plan.md).

`document_key()` derives a stable identity from `(tenant_id, source)` —
`Document.id` itself stays a random UUID per instance (unchanged, so nothing
elsewhere that depends on `Document.id` being fresh per parse breaks); the
lifecycle ledger keys on this instead, so re-parsing "the same" source
document (same tenant, same `source` path/URL) is recognized as the same
logical document across separate `ingest()` calls. `content_hash()` detects
whether that document's content actually changed since the last ingest.
"""
from modular_rag.core.document_identity import content_hash, document_key

__all__ = ["content_hash", "document_key"]
