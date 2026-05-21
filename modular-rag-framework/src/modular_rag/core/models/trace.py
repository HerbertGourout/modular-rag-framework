from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.ids import new_id


class TraceStep(BaseModel):
    name: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    id: str = Field(default_factory=new_id)
    query_id: str
    pipeline_id: str = ""
    steps: list[TraceStep] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    routing_strategy: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)
        self.total_latency_ms += step.latency_ms
        self.total_input_tokens += step.input_tokens
        self.total_output_tokens += step.output_tokens
