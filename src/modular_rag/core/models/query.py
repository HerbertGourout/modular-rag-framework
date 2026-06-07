from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import Modality, RoutingStrategy
from modular_rag.core.ids import new_id


class Query(BaseModel):
    id: str = Field(default_factory=new_id)
    text: str
    modality: Modality = Modality.TEXT
    routing_hint: RoutingStrategy | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}
