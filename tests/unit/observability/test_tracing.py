from __future__ import annotations

from modular_rag.observability import NullSpan, NullTracer


def test_null_tracer_name() -> None:
    assert NullTracer().name() == "null"


def test_null_tracer_start_span_is_a_true_no_op() -> None:
    tracer = NullTracer()

    with tracer.start_span("rag.retrieve", {"provider": "hybrid"}) as span:
        assert isinstance(span, NullSpan)
        span.set_attribute("chunks_returned", 5)
        span.record_error("ignored")
    # Nothing to assert beyond "this never raised" -- there is no exporter,
    # no state, nothing recorded anywhere. This is the disabled-tracing path
    # (ADR-0012's "instrumentation can be disabled" acceptance criterion).
