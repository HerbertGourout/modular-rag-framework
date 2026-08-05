from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.ids import new_id

TRACE_SCHEMA_VERSION = "1.1"  # bumped in Lot 10 (docs/refactoring-plan.md): fixed the
# double-counted generation-latency bug (orchestration/engine.py no longer adds its own
# wrapping "generate" step alongside the generator's own instrumentation). Existing
# consumers reading `steps` by name/latency should re-check any generation-latency
# aggregation logic against this version.


class TraceStep(BaseModel):
    name: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Trace(BaseModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    id: str = Field(default_factory=new_id)
    query_id: str
    pipeline_id: str = ""
    steps: list[TraceStep] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    routing_strategy: str = ""
    failed: bool = False
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def totals(self) -> dict[str, float | int]:
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "latency_ms": self.total_latency_ms,
        }

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)
        self.total_latency_ms += step.latency_ms
        self.total_input_tokens += step.input_tokens
        self.total_output_tokens += step.output_tokens
