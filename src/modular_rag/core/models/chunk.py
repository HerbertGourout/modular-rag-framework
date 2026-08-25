from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import Modality
from modular_rag.core.ids import new_id


class Chunk(BaseModel):
    id: str = Field(default_factory=new_id)
    doc_id: str
    content: str
    modality: Modality = Modality.TEXT
    embedding: list[float] | None = None
    embedding_text: str | None = None  # ingest-time-only: text to embed instead of `content`
    # when set (e.g. document-context-prefixed for retrieval quality, per "contextual
    # retrieval"-style enrichment). Never persisted to a store's payload and never shown in
    # citations/API responses (both read `content` directly) — discarded once `embedding` is
    # computed. `None` means "embed `content` as-is," the pre-existing behavior.
    start_char: int = 0
    end_char: int = 0
    page: int | None = None
    tenant_id: str | None = None  # Lot 11b: owning tenant; None (legacy/unclassified) is
    # treated as inaccessible by tenant-isolation filtering, not implicitly public.
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}

    @property
    def token_estimate(self) -> int:
        return len(self.content.split())
