from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.ids import new_id


class Citation(BaseModel):
    chunk_id: str
    source: str
    passage: str
    score: float
    page: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    id: str = Field(default_factory=new_id)
    query_id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float | None = None
    trace_id: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
