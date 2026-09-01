"""OpenTelemetry `Meter` adapter (ADR-0013).

Lot 12 (external plan — "Metrics, Dashboards, and SLO"; not this repository's
own `docs/refactoring-plan.md` Lot numbering).

`opentelemetry-sdk`/`opentelemetry-api`/`opentelemetry-exporter-otlp` are the
optional `v4` dependency group (`pyproject.toml`, already declared for Lot 11's
`OtelTracer`) — every symbol from them is imported lazily, inside method
bodies only, per the mandatory adapters lazy-import rule
(`.claude/rules/adapters.md`).
"""
from __future__ import annotations

import re
import threading
from collections.abc import Callable
from typing import Any

import structlog

from modular_rag.contracts.tracing import AttributeValue
from modular_rag.core.errors import ConfigurationError

log = structlog.get_logger(__name__)

# ADR-0013 cardinality safety: an *allowlist* of the small, closed set of
# label keys real call sites in this codebase actually pass (Codex review
# pass 1, HIGH-001). An earlier version only denylisted a fixed list of
# known-bad *keys* (`correlation_id`, `request_id`, ...) — that let an
# unanticipated identifier-shaped key (`tenant_id`, `user_id`, `email`,
# `session`, a raw URL, any non-UUID/ULID-shaped free-form value) straight
# through, since it was never denylisted. An allowlist closes that gap
# structurally: any key not explicitly known-bounded is dropped by default,
# regardless of what it's called. Extend this set only when a new call site
# needs a genuinely bounded, enumerable label (an operation/stage/status/
# model/source/type/direction/engine/state-style value) — never for anything
# request-, user-, session-, or tenant-scoped. Checked case-insensitively so
# a call-site casing slip doesn't accidentally admit an otherwise-safe key.
_ALLOWED_LABEL_KEYS = frozenset(
    {
        "operation",
        "engine",
        "status",
        "error_type",
        "stage",
        "source",
        "type",
        "direction",
        "model",
        "state",
    }
)

# A second, value-shaped check applied even to an allowed key: a UUID- or
# ULID-shaped *value* is never a legitimate bounded label (operation names,
# stage names, model identifiers, status codes are never UUID/ULID-shaped) —
# catches an identifier accidentally assigned to an otherwise-safe key.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$")


def _sanitize_attributes(
    attributes: dict[str, AttributeValue] | None,
) -> dict[str, AttributeValue]:
    """Drop (never raise on) any attribute whose key is not an explicitly
    allowlisted, bounded label, or whose value looks like a per-request
    identifier. Logs one warning per dropped key so a violation is
    discoverable without ever failing the caller's actual request."""
    if not attributes:
        return {}
    safe: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if key.lower() not in _ALLOWED_LABEL_KEYS:
            log.warning(
                "meter.dropped_high_cardinality_label", key=key, reason="key_not_allowlisted"
            )
            continue
        if isinstance(value, str) and (_UUID_RE.match(value) or _ULID_RE.match(value)):
            log.warning("meter.dropped_high_cardinality_label", key=key, reason="id_shaped_value")
            continue
        safe[key] = value
    return safe


class OtelMeter:
    """Real `Meter` (ADR-0013) backed by the OpenTelemetry SDK metrics API.

    `otlp_endpoint=None` (the default) creates real instruments — every
    counter/histogram/gauge call path is exercised identically in every
    environment — but attaches no exporter, so nothing is ever transmitted
    anywhere ("toggleable export": the toggle is whether an endpoint is
    configured, mirroring `OtelTracer`). Setting `otlp_endpoint` attaches a
    `PeriodicExportingMetricReader(OTLPMetricExporter(...))`, which exports
    asynchronously on its own schedule and catches/logs export failures
    internally rather than raising into application code — this, not any
    code in this file, is what satisfies "no functional impact if the
    exporter is unavailable."

    Instrument objects (`Counter`/`Histogram`/`Gauge`) are created once per
    distinct metric `name` and cached, not recreated on every call — the
    OTel SDK expects one instrument object per metric, reused across many
    `add()`/`record()`/`set()` calls.
    """

    def __init__(
        self,
        service_name: str = "modular-rag",
        otlp_endpoint: str | None = None,
        otlp_insecure: bool = True,
        console_export: bool = False,
        export_interval_millis: int = 60_000,
    ) -> None:
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.otlp_insecure = otlp_insecure
        self.console_export = console_export
        self.export_interval_millis = export_interval_millis
        self._meter: Any = None
        self._provider: Any = None
        self._instruments: dict[tuple[str, str], Any] = {}
        # Codex review pass 1 (MEDIUM-002) precedent, applied here from the start
        # rather than discovered by a second review round: `_get_meter()`/
        # `_get_instrument()` are single-flight, double-checked-locking builds —
        # see OtelTracer's own `_get_tracer()` for the reasoning this mirrors.
        self._build_lock = threading.Lock()

    def name(self) -> str:
        return "otel"

    def close(self) -> None:
        """Flush and shut down the underlying `MeterProvider`, if one was
        ever built. Called generically by `Container.close()` — without
        this, a pending periodic-export batch could be silently lost on
        process exit rather than exported."""
        if self._provider is not None:
            self._provider.shutdown()

    def _get_meter(self) -> Any:
        if self._meter is None:
            with self._build_lock:
                if self._meter is None:
                    self._meter = self._build_meter()
        return self._meter

    def _build_meter(self) -> Any:
        try:
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        except ImportError as exc:
            raise ConfigurationError(
                "OtelMeter requires the 'v4' optional dependency group "
                "(pip install modular-rag[v4]) — opentelemetry-sdk is not installed."
            ) from exc

        readers = []
        if self.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            exporter = OTLPMetricExporter(endpoint=self.otlp_endpoint, insecure=self.otlp_insecure)
            readers.append(
                PeriodicExportingMetricReader(
                    exporter, export_interval_millis=self.export_interval_millis
                )
            )
        if self.console_export:
            from opentelemetry.sdk.metrics.export import (
                ConsoleMetricExporter,
                PeriodicExportingMetricReader,
            )

            readers.append(
                PeriodicExportingMetricReader(
                    ConsoleMetricExporter(), export_interval_millis=self.export_interval_millis
                )
            )
        provider = MeterProvider(
            resource=Resource.create({SERVICE_NAME: self.service_name}), metric_readers=readers
        )
        self._provider = provider
        return provider.get_meter(self.service_name)

    def _get_instrument(self, kind: str, name: str) -> Any:
        cache_key = (kind, name)
        if cache_key not in self._instruments:
            # `_get_meter()` is called *before* acquiring `_build_lock`, not
            # inside the critical section below -- it takes the same lock
            # internally, and `threading.Lock` is not reentrant. An earlier
            # version called it from inside `with self._build_lock:`, which
            # self-deadlocked on the very first counter()/histogram()/gauge()
            # call against a fresh `OtelMeter()` (caught by this file's own
            # test suite hanging, not by a review round).
            meter = self._get_meter()
            with self._build_lock:
                if cache_key not in self._instruments:
                    creator = getattr(meter, f"create_{kind}")
                    self._instruments[cache_key] = creator(name)
        return self._instruments[cache_key]

    def counter(
        self, name: str, value: int | float = 1, attributes: dict[str, AttributeValue] | None = None
    ) -> None:
        safe_attributes = _sanitize_attributes(attributes)
        self._emit(
            "counter", name, lambda instrument: instrument.add(value, attributes=safe_attributes)
        )

    def histogram(
        self, name: str, value: float, attributes: dict[str, AttributeValue] | None = None
    ) -> None:
        safe_attributes = _sanitize_attributes(attributes)
        self._emit(
            "histogram",
            name,
            lambda instrument: instrument.record(value, attributes=safe_attributes),
        )

    def gauge(
        self, name: str, value: float, attributes: dict[str, AttributeValue] | None = None
    ) -> None:
        safe_attributes = _sanitize_attributes(attributes)
        self._emit(
            "gauge", name, lambda instrument: instrument.set(value, attributes=safe_attributes)
        )

    def _emit(self, kind: str, name: str, record: Callable[[Any], None]) -> None:
        """Shared never-raise emission path (Codex review pass 1, HIGH-002):
        the `Meter` Protocol's own documented contract ("must not raise for a
        normal call, even when the underlying export backend is unreachable
        -- the caller's business logic must never fail because metrics
        emission failed") applies to instrument creation/lazy SDK
        initialization too, not only to the final `add()`/`record()`/`set()`
        call -- an earlier version let a missing-SDK `ConfigurationError`
        (or any OTel-internal failure) propagate straight out of
        `counter()`/`histogram()`/`gauge()` into the caller's request path.
        Every failure is logged once, at warning level, and the metric is
        silently dropped -- callers cannot distinguish "recorded" from
        "dropped due to backend failure" by design, matching the same
        best-effort posture `Tracer`/`AuditSink` already apply."""
        try:
            instrument = self._get_instrument(kind, name)
            record(instrument)
        except Exception as exc:
            log.warning(
                "meter.emission_failed", kind=kind, name=name, error_type=type(exc).__name__
            )

    @classmethod
    def for_testing(cls, service_name: str = "modular-rag-test") -> tuple[OtelMeter, Any]:
        """Build an `OtelMeter` wired to an in-process `InMemoryMetricReader`
        instead of OTLP — this is the "test using an in-memory exporter"
        requirement, mirroring `OtelTracer.for_testing()`.

        Returns `(meter, reader)` — call `reader.get_metrics_data()` to
        inspect what was recorded (a real `MetricsData` tree; walk
        `.resource_metrics[0].scope_metrics[0].metrics` for individual
        counters/histograms/gauges).
        """
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource

        meter = cls(service_name=service_name)
        reader = InMemoryMetricReader()
        provider = MeterProvider(
            resource=Resource.create({SERVICE_NAME: service_name}), metric_readers=[reader]
        )
        meter._provider = provider
        meter._meter = provider.get_meter(service_name)
        return meter, reader
