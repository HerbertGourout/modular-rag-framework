from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import Modality
from modular_rag.core.ids import new_id


class Query(BaseModel):
    id: str = Field(default_factory=new_id)
    text: str
    modality: Modality = Modality.TEXT
    tenant_id: str | None = None  # Lot 11b: None until a caller authenticates; enforcement
    # (deny-by-default when unset) lives in security/policies/tenant_isolation.py, not here.
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}
