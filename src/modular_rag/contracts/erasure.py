"""Right-to-erasure proof (Lot 12c, docs/refactoring-plan.md — "right-to-erasure
proof (including a verified restore exercise, not just a backup that has
never been tested)").

`ErasureProof` is deliberately not just "we called delete()": it records
whether each store was *re-checked after deletion* and found to actually be
missing the erased ids — `verified_absent_from_lexical` is `None`, not
`True`, when the retriever doesn't support `list_ids()` at all (honest
"could not verify," never conflated with "verified and clean").
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ErasureProof(BaseModel):
    document_key: str
    chunk_ids_removed: list[str] = Field(default_factory=list)
    verified_absent_from_vector: bool
    verified_absent_from_lexical: bool | None  # None: retriever doesn't support list_ids()
    tombstoned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    proof_hash: str

    @property
    def fully_verified(self) -> bool:
        """True only when every store that *could* be checked came back
        clean. A retriever that can't be checked (`None`) does not count as
        a failure, but also does not count as proof — see
        `verified_absent_from_lexical`'s own docstring."""
        return self.verified_absent_from_vector and self.verified_absent_from_lexical is not False
