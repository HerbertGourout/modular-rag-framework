from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import DataClassification, Modality
from modular_rag.core.ids import new_id


class Document(BaseModel):
    id: str = Field(default_factory=new_id)
    source: str
    content: str
    modality: Modality = Modality.TEXT
    mime_type: str = "text/plain"
    tenant_id: str | None = None  # Lot 11b: owning tenant; see Chunk.tenant_id for the
    # fail-closed handling of an unset value once tenant-isolation enforcement is configured.
    classification: DataClassification | None = None  # Lot 20: explicit, caller-supplied
    # sensitivity level (docs/architecture/data-classification-policy.md) -- this codebase
    # does not infer it. `None` (unclassified) is not treated as `PUBLIC`; a configured
    # `governance.egress_policy` defaults an unclassified chunk to its own
    # `default_classification` (deny-by-default, restricted unless the operator says
    # otherwise) before deciding whether it may reach a remote embedder. Propagated onto
    # each `Chunk` this document produces by `ingestion.pipelines.default`'s chunking step.
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
