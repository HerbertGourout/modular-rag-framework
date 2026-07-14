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
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
