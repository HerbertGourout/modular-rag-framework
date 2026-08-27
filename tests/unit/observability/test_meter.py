from __future__ import annotations

from modular_rag.observability import NullMeter


def test_null_meter_name() -> None:
    assert NullMeter().name() == "null"


def test_null_meter_counter_histogram_gauge_are_true_no_ops() -> None:
    meter = NullMeter()

    meter.counter("mrag.request.errors", attributes={"operation": "answer"})
    meter.histogram("mrag.request.duration_ms", 42.0, attributes={"operation": "answer"})
    meter.gauge("mrag.review.pending", 3.0)
    # Nothing to assert beyond "this never raised" -- there is no exporter,
    # no state, nothing recorded anywhere. This is the disabled-metrics path
    # (ADR-0013's "instrumentation can be disabled" acceptance criterion).
