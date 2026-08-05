from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import Modality
from modular_rag.core.ids import new_id


class Document(BaseModel):
    id: str = Field(default_factory=new_id)
    source: str
    content: str
    modality: Modality = Modality.TEXT
    mime_type: str = "text/plain"
    tenant_id: str | None = None  # Lot 11b: owning tenant; see Chunk.tenant_id for the
    # fail-closed handling of an unset value once tenant-isolation enforcement is configured.
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
