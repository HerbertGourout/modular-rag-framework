"""Protocol conformance tests for Telemetry (contracts/telemetry.py)."""
from __future__ import annotations

import pytest

from modular_rag.contracts.telemetry import Telemetry
from modular_rag.core.models.metrics import Metrics
from modular_rag.core.models.trace import Trace
from modular_rag.observability import NullTelemetry, StructlogTelemetry

TELEMETRY_FACTORIES = [StructlogTelemetry, NullTelemetry]


@pytest.mark.parametrize("telemetry_factory", TELEMETRY_FACTORIES)
def test_telemetry_satisfies_the_protocol(telemetry_factory: type) -> None:
    assert isinstance(telemetry_factory(), Telemetry)


@pytest.mark.parametrize("telemetry_factory", TELEMETRY_FACTORIES)
def test_telemetry_has_a_name(telemetry_factory: type) -> None:
    assert telemetry_factory().name()


@pytest.mark.parametrize("telemetry_factory", TELEMETRY_FACTORIES)
def test_record_trace_does_not_raise(telemetry_factory: type) -> None:
    telemetry_factory().record_trace(Trace(query_id="q-1"))


@pytest.mark.parametrize("telemetry_factory", TELEMETRY_FACTORIES)
def test_record_metrics_does_not_raise(telemetry_factory: type) -> None:
    telemetry_factory().record_metrics("pipeline-1", Metrics())
