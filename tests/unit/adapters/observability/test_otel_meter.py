"""Unit tests for OtelMeter (adapters/observability/otel_meter.py, ADR-0013).

Uses `OtelMeter.for_testing()` — an in-process `InMemoryMetricReader` — per
the task's own "test using an in-memory exporter" requirement. No network,
no real OTLP collector.
"""
from __future__ import annotations

import threading
from typing import Any

import pytest
import structlog

from modular_rag.adapters.observability.otel_meter import OtelMeter


def _metrics_by_name(reader: Any) -> dict[str, Any]:
    """Flatten `InMemoryMetricReader.get_metrics_data()`'s nested resource ->
    scope -> metric tree into `{metric_name: Metric}` for easy assertions."""
    data = reader.get_metrics_data()
    if data is None:
        return {}
    out: dict[str, Any] = {}
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                out[metric.name] = metric
    return out


def test_counter_records_a_data_point_with_attributes() -> None:
    meter, reader = OtelMeter.for_testing()

    meter.counter("mrag.request.errors", attributes={"operation": "answer"})

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.errors"].data.data_points[0]
    assert point.value == 1
    assert point.attributes == {"operation": "answer"}


def test_counter_accepts_an_explicit_value() -> None:
    meter, reader = OtelMeter.for_testing()

    meter.counter("mrag.ingest.chunks", 42)

    metrics = _metrics_by_name(reader)
    assert metrics["mrag.ingest.chunks"].data.data_points[0].value == 42


def test_counter_calls_accumulate_into_the_same_time_series() -> None:
    """Two `counter()` calls with the same name+attributes must add, not
    overwrite -- this is what makes it a *counter* rather than a gauge."""
    meter, reader = OtelMeter.for_testing()

    meter.counter("mrag.guard.rejections", attributes={"stage": "query"})
    meter.counter("mrag.guard.rejections", attributes={"stage": "query"})
    meter.counter("mrag.guard.rejections", attributes={"stage": "query"})

    metrics = _metrics_by_name(reader)
    assert metrics["mrag.guard.rejections"].data.data_points[0].value == 3


def test_histogram_records_the_observed_value() -> None:
    meter, reader = OtelMeter.for_testing()

    meter.histogram("mrag.request.duration_ms", 123.4, attributes={"operation": "answer"})

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.duration_ms"].data.data_points[0]
    assert point.sum == pytest.approx(123.4)
    assert point.count == 1


def test_gauge_records_the_current_value() -> None:
    meter, reader = OtelMeter.for_testing()

    meter.gauge("mrag.review.pending", 3.0)

    metrics = _metrics_by_name(reader)
    assert metrics["mrag.review.pending"].data.data_points[0].value == 3.0


def test_gauge_calls_overwrite_not_accumulate() -> None:
    """A gauge's whole point: the *latest* value wins, unlike a counter."""
    meter, reader = OtelMeter.for_testing()

    meter.gauge("mrag.readiness.state", 1, attributes={"state": "healthy"})
    meter.gauge("mrag.readiness.state", 1, attributes={"state": "degraded"})

    metrics = _metrics_by_name(reader)
    points = metrics["mrag.readiness.state"].data.data_points
    # Both attribute sets are distinct time series -- both present, each
    # holding its own last-set value (never summed).
    by_state = {p.attributes["state"]: p.value for p in points}
    assert by_state == {"healthy": 1, "degraded": 1}


def test_repeated_calls_reuse_the_same_cached_instrument() -> None:
    """Instruments are created once per (kind, name) and cached -- not
    rebuilt on every call, matching the OTel SDK's own "one instrument
    object, many observations" model."""
    meter, _reader = OtelMeter.for_testing()

    meter.counter("mrag.request.errors")
    meter.counter("mrag.request.errors")

    assert len(meter._instruments) == 1


# ---------------------------------------------------------------------------
# ADR-0013 cardinality safety: the explicit "No unbounded cardinality"
# acceptance criterion, enforced (not just documented) via an *allowlist* of
# known-bounded label keys + a UUID/ULID-shaped-value check, applied to every
# counter/histogram/gauge call. Codex review pass 1 (HIGH-001): a prior
# denylist-only version let any key it didn't anticipate -- tenant_id,
# user_id, email, session, a raw URL -- straight through unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unlisted_key",
    [
        "correlation_id",
        "request_id",
        "trace_id",
        "query_id",
        "chunk_id",
        "doc_id",
        "CORRELATION_ID",
    ],
)
def test_previously_forbidden_keys_are_still_dropped(unlisted_key: str) -> None:
    meter, reader = OtelMeter.for_testing()

    meter.counter(
        "mrag.request.errors", attributes={unlisted_key: "some-value", "operation": "answer"}
    )

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.errors"].data.data_points[0]
    assert unlisted_key not in point.attributes
    assert unlisted_key.lower() not in point.attributes
    assert point.attributes == {"operation": "answer"}


@pytest.mark.parametrize(
    "arbitrary_key",
    ["tenant_id", "user_id", "email", "session", "session_id", "url", "ip_address", "username"],
)
def test_arbitrary_unbounded_keys_are_dropped_not_raised(arbitrary_key: str) -> None:
    """The exact gap Codex found: none of these were on the old denylist, so
    they passed straight through. The allowlist drops them by default
    instead of requiring each one to be individually anticipated."""
    meter, reader = OtelMeter.for_testing()

    meter.counter(
        "mrag.request.errors",
        attributes={arbitrary_key: "some-unbounded-value", "operation": "answer"},
    )

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.errors"].data.data_points[0]
    assert arbitrary_key not in point.attributes
    assert point.attributes == {"operation": "answer"}


def test_uuid_shaped_values_are_dropped_even_under_an_unlisted_key() -> None:
    """Defense in depth: an identifier slipping through under a key this
    file's denylist didn't anticipate is still caught by its *shape*."""
    meter, reader = OtelMeter.for_testing()

    meter.counter(
        "mrag.request.errors",
        attributes={
            "some_future_field": "550e8400-e29b-41d4-a716-446655440000",
            "operation": "answer",
        },
    )

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.errors"].data.data_points[0]
    assert "some_future_field" not in point.attributes
    assert point.attributes == {"operation": "answer"}


def test_bounded_labels_are_never_dropped() -> None:
    """The safety net must not be so aggressive it eats legitimate,
    bounded-cardinality labels -- operation names, stages, models, statuses,
    engines all pass through untouched."""
    meter, reader = OtelMeter.for_testing()

    meter.counter(
        "mrag.request.errors",
        attributes={
            "operation": "answer",
            "engine": "native",
            "status": "error",
            "model": "gpt-4o-mini",
            "error_type": "SecurityError",
        },
    )

    metrics = _metrics_by_name(reader)
    point = metrics["mrag.request.errors"].data.data_points[0]
    assert point.attributes == {
        "operation": "answer",
        "engine": "native",
        "status": "error",
        "model": "gpt-4o-mini",
        "error_type": "SecurityError",
    }


def test_no_attributes_at_all_does_not_raise() -> None:
    meter, reader = OtelMeter.for_testing()

    meter.counter("mrag.review.enqueued")

    metrics = _metrics_by_name(reader)
    assert metrics["mrag.review.enqueued"].data.data_points[0].value == 1


# ---------------------------------------------------------------------------
# Lifecycle: mirrors OtelTracer's own equivalent tests exactly (ADR-0012
# precedent) -- disabled export, concurrent lazy init, close(), missing SDK.
# ---------------------------------------------------------------------------


def test_disabled_export_still_creates_instruments_but_transmits_nothing() -> None:
    meter = OtelMeter()  # no otlp_endpoint, no console_export

    meter.counter("mrag.request.errors", attributes={"operation": "answer"})
    # No exception, no export target configured -- nothing to assert on
    # beyond "this didn't raise."


def test_concurrent_first_calls_build_exactly_one_meter_provider() -> None:
    """Same race-safety precedent as OtelTracer's `_get_tracer()` (Codex
    review pass 1, MEDIUM-002) -- applied here from the start rather than
    discovered by a second review round."""
    meter = OtelMeter()
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    results: list[object] = [None] * thread_count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = meter._get_meter()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(r) for r in results}) == 1, "every thread must observe the same meter"
    assert meter._provider is not None


def test_close_shuts_down_the_provider_if_one_was_built() -> None:
    meter, _reader = OtelMeter.for_testing()
    shutdown_calls = []
    meter._provider.shutdown = lambda: shutdown_calls.append(True)  # type: ignore[method-assign]

    meter.close()

    assert shutdown_calls == [True]


def test_close_is_a_no_op_when_no_metric_was_ever_recorded() -> None:
    OtelMeter().close()  # must not raise -- provider was never built


def test_missing_opentelemetry_sdk_logs_a_warning_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex review pass 1 (HIGH-002): the `Meter` Protocol's own documented
    contract says emission "must not raise ... even when the underlying
    export backend is unreachable" -- a missing SDK is exactly that class of
    failure, not grounds to fail the caller's business logic. An earlier
    version of this test asserted the opposite (a bare `pytest.raises`),
    which is what let the contract violation ship undetected."""
    import sys

    meter = OtelMeter()
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", None)

    with structlog.testing.capture_logs() as logs:
        meter.counter("mrag.request.errors")  # must not raise

    assert any(entry.get("event") == "meter.emission_failed" for entry in logs)


def test_instrument_call_failure_is_swallowed_not_raised() -> None:
    """Codex review pass 1 (HIGH-002), second half: the contract's "must not
    raise" applies to the actual `add()`/`record()`/`set()` call too, not
    only to instrument creation/lazy SDK init."""
    meter, _reader = OtelMeter.for_testing()
    instrument = meter._get_instrument("counter", "mrag.request.errors")
    instrument.add = lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("backend unreachable"))

    with structlog.testing.capture_logs() as logs:
        meter.counter("mrag.request.errors")  # must not raise

    assert any(entry.get("event") == "meter.emission_failed" for entry in logs)


def test_name_returns_otel() -> None:
    assert OtelMeter().name() == "otel"
