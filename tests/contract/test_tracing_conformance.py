"""Protocol conformance tests for Tracer/Span (contracts/tracing.py, ADR-0012)."""
from __future__ import annotations

import pytest

from modular_rag.contracts.tracing import Span, Tracer
from modular_rag.observability import NullTracer

TRACER_FACTORIES = [NullTracer]


@pytest.mark.parametrize("tracer_factory", TRACER_FACTORIES)
def test_tracer_satisfies_the_protocol(tracer_factory: type) -> None:
    assert isinstance(tracer_factory(), Tracer)


@pytest.mark.parametrize("tracer_factory", TRACER_FACTORIES)
def test_tracer_has_a_name(tracer_factory: type) -> None:
    assert tracer_factory().name()


@pytest.mark.parametrize("tracer_factory", TRACER_FACTORIES)
def test_start_span_does_not_raise(tracer_factory: type) -> None:
    tracer = tracer_factory()
    with tracer.start_span("test.op", {"k": 1}) as span:
        assert isinstance(span, Span)
        span.set_attribute("another", "value")
        span.record_error("SomeError")


def test_otel_tracer_satisfies_the_protocol() -> None:
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    assert isinstance(OtelTracer(), Tracer)


def test_otel_tracer_has_a_name() -> None:
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    assert OtelTracer().name() == "otel"


def test_otel_tracer_start_span_does_not_raise() -> None:
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, _exporter = OtelTracer.for_testing()
    with tracer.start_span("test.op", {"k": 1}) as span:
        assert isinstance(span, Span)
        span.set_attribute("another", "value")
