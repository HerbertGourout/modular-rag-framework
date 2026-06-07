from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.trace import Trace


@runtime_checkable
class Telemetry(Protocol):
    """Emit execution traces and aggregate metrics to an observability backend."""

    def record_trace(self, trace: Trace) -> None: ...

    def record_metrics(self, pipeline_id: str, metrics: Metrics) -> None: ...

    def name(self) -> str: ...
