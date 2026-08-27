from __future__ import annotations

import structlog

from modular_rag.contracts.tracing import AttributeValue
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


class NullSpan:
    """No-op `Span` (ADR-0012) — returned by `NullTracer.start_span()`."""

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        pass

    def record_error(self, message: str) -> None:
        pass

    def __enter__(self) -> NullSpan:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        pass


class NullTracer:
    """No-op tracer for testing and for explicitly disabling tracing
    (`observability.tracer.type: null` — symmetrical with `telemetry`'s
    `NullTelemetry`)."""

    def name(self) -> str:
        return "null"

    def start_span(self, name: str, attributes: dict[str, AttributeValue] | None = None) -> NullSpan:
        return NullSpan()


class NullMeter:
    """No-op meter (ADR-0013) for testing and for explicitly disabling
    metrics (`observability.meter.type: null` — symmetrical with
    `telemetry`'s `NullTelemetry` and `tracer`'s `NullTracer`)."""

    def name(self) -> str:
        return "null"

    def counter(
        self, name: str, value: int | float = 1, attributes: dict[str, AttributeValue] | None = None
    ) -> None:
        pass

    def histogram(
        self, name: str, value: float, attributes: dict[str, AttributeValue] | None = None
    ) -> None:
        pass

    def gauge(self, name: str, value: float, attributes: dict[str, AttributeValue] | None = None) -> None:
        pass


__all__ = [
    "StructlogTelemetry",
    "NullTelemetry",
    "NullSpan",
    "NullTracer",
    "NullMeter",
]
