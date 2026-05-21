from __future__ import annotations

import structlog

from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.trace import Trace


class StructlogTelemetry:
    """Log traces and metrics as structured JSON via structlog."""

    def name(self) -> str:
        return "structlog"

    def record_trace(self, trace: Trace) -> None:
        structlog.get_logger("telemetry").info(
            "trace",
            trace_id=trace.id,
            query_id=trace.query_id,
            pipeline_id=trace.pipeline_id,
            latency_ms=trace.total_latency_ms,
            input_tokens=trace.total_input_tokens,
            output_tokens=trace.total_output_tokens,
            steps=[s.name for s in trace.steps],
        )

    def record_metrics(self, pipeline_id: str, metrics: Metrics) -> None:
        structlog.get_logger("telemetry").info(
            "metrics",
            pipeline_id=pipeline_id,
            **metrics.summary(),
        )


class NullTelemetry:
    """No-op telemetry for testing."""

    def name(self) -> str:
        return "null"

    def record_trace(self, trace: Trace) -> None:
        pass

    def record_metrics(self, pipeline_id: str, metrics: Metrics) -> None:
        pass


__all__ = ["StructlogTelemetry", "NullTelemetry"]
