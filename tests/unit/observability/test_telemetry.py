from __future__ import annotations

import structlog

from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.observability import NullTelemetry, StructlogTelemetry


def _trace() -> Trace:
    trace = Trace(query_id="q-1", pipeline_id="local-hybrid-rag")
    trace.add_step(TraceStep(name="retrieve", latency_ms=12.5, input_tokens=0, output_tokens=0))
    return trace


def test_structlog_telemetry_name() -> None:
    assert StructlogTelemetry().name() == "structlog"


def test_structlog_telemetry_record_trace_logs_expected_fields() -> None:
    with structlog.testing.capture_logs() as logs:
        StructlogTelemetry().record_trace(_trace())

    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "trace"
    assert event["trace_id"]
    assert event["query_id"] == "q-1"
    assert event["pipeline_id"] == "local-hybrid-rag"
    assert event["steps"] == ["retrieve"]


def test_structlog_telemetry_record_metrics_logs_only_set_fields() -> None:
    metrics = Metrics(exact_match=1.0)

    with structlog.testing.capture_logs() as logs:
        StructlogTelemetry().record_metrics("local-hybrid-rag", metrics)

    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "metrics"
    assert event["pipeline_id"] == "local-hybrid-rag"
    assert event["exact_match"] == 1.0
    assert "recall_at_k" not in event  # unset fields are excluded by Metrics.summary()


def test_null_telemetry_name() -> None:
    assert NullTelemetry().name() == "null"


def test_null_telemetry_record_trace_is_a_true_no_op() -> None:
    with structlog.testing.capture_logs() as logs:
        NullTelemetry().record_trace(_trace())

    assert logs == []


def test_null_telemetry_record_metrics_is_a_true_no_op() -> None:
    with structlog.testing.capture_logs() as logs:
        NullTelemetry().record_metrics("local-hybrid-rag", Metrics())

    assert logs == []
