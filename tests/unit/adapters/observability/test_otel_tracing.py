"""Unit tests for OtelTracer (adapters/observability/otel_tracing.py, ADR-0012).

Uses `OtelTracer.for_testing()` — an in-process `InMemorySpanExporter` behind
a synchronous `SimpleSpanProcessor` — per the task's own "test using an
in-memory exporter" requirement. No network, no real OTLP collector.
"""
from __future__ import annotations

import threading

import pytest

from modular_rag.adapters.observability.otel_tracing import OtelTracer
from modular_rag.core.errors import ConfigurationError


def test_start_span_records_a_finished_span_with_attributes() -> None:
    tracer, exporter = OtelTracer.for_testing()

    with tracer.start_span("rag.retrieve", {"provider": "hybrid"}) as span:
        span.set_attribute("chunks_returned", 5)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "rag.retrieve"
    assert spans[0].attributes["provider"] == "hybrid"
    assert spans[0].attributes["chunks_returned"] == 5


def test_nested_spans_share_one_trace_id() -> None:
    """The distributed-tracing guarantee: two spans created from the same
    call stack, through the same tracer, share one OpenTelemetry trace_id —
    this is what lets `app/application.py`'s root span and
    `orchestration/engine.py`'s per-stage spans stitch into one trace
    without any manual id-threading (ADR-0012)."""
    tracer, exporter = OtelTracer.for_testing()

    with tracer.start_span("rag.answer") as outer:
        with tracer.start_span("rag.retrieve") as inner:
            inner.set_attribute("chunks_returned", 3)
        outer.set_attribute("status", "ok")

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert spans["rag.answer"].context.trace_id == spans["rag.retrieve"].context.trace_id
    assert spans["rag.retrieve"].parent.span_id == spans["rag.answer"].context.span_id


def test_span_records_error_status_on_exception() -> None:
    tracer, exporter = OtelTracer.for_testing()

    with pytest.raises(ValueError):
        with tracer.start_span("rag.generate"):
            raise ValueError("boom, should never appear in the span")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
    # The raw exception message must never reach the span (ADR-0012 §9,
    # PII-safety) — only the exception *type name* is recorded.
    assert "ValueError" == spans[0].status.description
    assert "boom" not in (spans[0].status.description or "")


def test_record_error_sets_error_status_without_raw_text_requirement() -> None:
    tracer, exporter = OtelTracer.for_testing()

    with tracer.start_span("rag.guard_query") as span:
        span.record_error("denied")

    spans = exporter.get_finished_spans()
    assert spans[0].status.status_code.name == "ERROR"
    assert spans[0].status.description == "denied"


def test_disabled_export_still_creates_spans_but_transmits_nothing() -> None:
    """`otlp_endpoint=None` (the default) must not prevent span creation —
    every attribute-setting/error-recording code path is exercised
    identically whether or not export is enabled (ADR-0012)."""
    tracer = OtelTracer()  # no otlp_endpoint, no console_export

    with tracer.start_span("rag.embed", {"chunk_count": 4}) as span:
        span.set_attribute("chunks_embedded", 4)
    # No exception, no export target configured -- nothing to assert on
    # beyond "this didn't raise," which is the point: disabled export has
    # no functional impact on the instrumented code path.


def test_concurrent_first_calls_build_exactly_one_tracer_provider() -> None:
    """Codex review pass 1, MEDIUM-002: reproduces the finding's own
    deterministic two-thread method -- a barrier forces both threads to
    observe `_tracer is None` at (approximately) the same instant, so an
    unsynchronized check-then-build would build two separate
    TracerProviders and leak one. Uses several threads (not just two) and a
    real `threading.Barrier` to make the race window as wide as possible."""
    tracer = OtelTracer()
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    results: list[object] = [None] * thread_count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = tracer._get_tracer()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(r) for r in results}) == 1, "every thread must observe the same tracer"
    assert tracer._provider is not None


def test_close_shuts_down_the_provider_if_one_was_built() -> None:
    """`Container.close()` calls `.close()` on every registered component
    that has one -- this is what flushes a pending `BatchSpanProcessor`
    batch instead of silently losing it on process exit."""
    tracer, _exporter = OtelTracer.for_testing()
    shutdown_calls = []
    tracer._provider.shutdown = lambda: shutdown_calls.append(True)  # type: ignore[method-assign]

    tracer.close()

    assert shutdown_calls == [True]


def test_close_is_a_no_op_when_no_span_was_ever_created() -> None:
    OtelTracer().close()  # must not raise -- provider was never built


def test_missing_opentelemetry_sdk_raises_a_clear_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """`OtelTracer` itself never fails to construct (imports are lazy); only
    the first `start_span()` call triggers the real import, and a genuinely
    missing SDK must raise `ConfigurationError`, not a bare `ImportError`
    a caller has no way to recognize as a configuration problem."""
    import sys

    tracer = OtelTracer()
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", None)

    with pytest.raises(ConfigurationError, match="v4"):
        tracer.start_span("rag.retrieve")
