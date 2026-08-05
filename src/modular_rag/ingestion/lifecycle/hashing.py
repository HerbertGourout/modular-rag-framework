"""Document-identity helpers (Lot 12a, docs/refactoring-plan.md).

`document_key()` derives a stable identity from `(tenant_id, source)` —
`Document.id` itself stays a random UUID per instance (unchanged, so nothing
elsewhere that depends on `Document.id` being fresh per parse breaks); the
lifecycle ledger keys on this instead, so re-parsing "the same" source
document (same tenant, same `source` path/URL) is recognized as the same
logical document across separate `ingest()` calls. `content_hash()` detects
whether that document's content actually changed since the last ingest.
"""
from __future__ import annotations

import hashlib


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def document_key(source: str, tenant_id: str | None = None) -> str:
    raw = f"{tenant_id or 'default'}:{source}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
