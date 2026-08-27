"""Protocol conformance tests for Meter (contracts/meter.py, ADR-0013)."""
from __future__ import annotations

import pytest

from modular_rag.contracts.meter import Meter
from modular_rag.observability import NullMeter

METER_FACTORIES = [NullMeter]


@pytest.mark.parametrize("meter_factory", METER_FACTORIES)
def test_meter_satisfies_the_protocol(meter_factory: type) -> None:
    assert isinstance(meter_factory(), Meter)


@pytest.mark.parametrize("meter_factory", METER_FACTORIES)
def test_meter_has_a_name(meter_factory: type) -> None:
    assert meter_factory().name()


@pytest.mark.parametrize("meter_factory", METER_FACTORIES)
def test_counter_histogram_gauge_do_not_raise(meter_factory: type) -> None:
    meter = meter_factory()
    meter.counter("mrag.test.counter", attributes={"k": "v"})
    meter.counter("mrag.test.counter", 5)
    meter.histogram("mrag.test.histogram", 12.5, attributes={"k": "v"})
    meter.gauge("mrag.test.gauge", 3.0, attributes={"k": "v"})


def test_otel_meter_satisfies_the_protocol() -> None:
    from modular_rag.adapters.observability.otel_meter import OtelMeter

    assert isinstance(OtelMeter(), Meter)


def test_otel_meter_has_a_name() -> None:
    from modular_rag.adapters.observability.otel_meter import OtelMeter

    assert OtelMeter().name() == "otel"


def test_otel_meter_counter_histogram_gauge_do_not_raise() -> None:
    from modular_rag.adapters.observability.otel_meter import OtelMeter

    meter, _reader = OtelMeter.for_testing()
    meter.counter("mrag.test.counter", attributes={"k": "v"})
    meter.histogram("mrag.test.histogram", 12.5, attributes={"k": "v"})
    meter.gauge("mrag.test.gauge", 3.0, attributes={"k": "v"})
