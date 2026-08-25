"""OpenTelemetry `Tracer` adapter (ADR-0012).

Lot 11 (external plan — "OpenTelemetry"; **not** this repository's own
`docs/refactoring-plan.md` Lot 11a/b/c sequence, which is unrelated,
already-completed tenant-isolation/redaction/audit work).

`opentelemetry-sdk`/`opentelemetry-api`/`opentelemetry-exporter-otlp` are the
optional `v4` dependency group (`pyproject.toml`) — every symbol from them is
imported lazily, inside method bodies only, per the mandatory adapters
lazy-import rule (`.claude/rules/adapters.md`).
"""
from __future__ import annotations

import threading
from typing import Any

from modular_rag.contracts.tracing import AttributeValue
from modular_rag.core.errors import ConfigurationError


class _OtelSpan:
    """Wraps the context manager returned by `Tracer.start_as_current_span()`
    so `__enter__`/`__exit__` drive the real OpenTelemetry span lifecycle,
    while `set_attribute`/`record_error` translate to the real OTel span API
    only once a span is active."""

    def __init__(self, span_cm: Any) -> None:
        self._cm = span_cm
        self._span: Any = None

    def __enter__(self) -> _OtelSpan:
        self._span = self._cm.__enter__()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None and self._span is not None:
            from opentelemetry.trace import Status, StatusCode

            # Only the exception *type name* is recorded — never str(exc_val),
            # which could embed request/response content (ADR-0012 §9).
            self._span.set_status(Status(StatusCode.ERROR, getattr(exc_type, "__name__", "error")))
        self._cm.__exit__(exc_type, exc_val, exc_tb)

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        if self._span is not None:
            self._span.set_attribute(key, value)

    def record_error(self, message: str) -> None:
        if self._span is not None:
            from opentelemetry.trace import Status, StatusCode

            self._span.set_status(Status(StatusCode.ERROR, message))


class OtelTracer:
    """Real `Tracer` (ADR-0012) backed by the OpenTelemetry SDK.

    `otlp_endpoint=None` (the default) creates real spans — every
    attribute-setting/error-recording code path is exercised identically in
    every environment — but attaches no exporter, so nothing is ever
    transmitted anywhere ("export via OTLP with a toggleable export
    function": the toggle is whether an endpoint is configured). Setting
    `otlp_endpoint` attaches a `BatchSpanProcessor(OTLPSpanExporter(...))`;
    `BatchSpanProcessor` exports asynchronously on a background thread and
    catches/logs export failures internally rather than raising into
    application code — this, not any code in this file, is what satisfies
    "no functional impact if the exporter is unavailable."
    """

    def __init__(
        self,
        service_name: str = "modular-rag",
        otlp_endpoint: str | None = None,
        otlp_insecure: bool = True,
        console_export: bool = False,
    ) -> None:
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.otlp_insecure = otlp_insecure
        self.console_export = console_export
        self._tracer: Any = None
        self._provider: Any = None
        # Codex review pass 1 (MEDIUM-002): `_get_tracer()` used to be an
        # unsynchronized check-then-build. A deterministic two-thread
        # reproduction (barrier around `_build_tracer()`) confirmed two
        # concurrent first calls could each observe `_tracer is None`,
        # build a separate TracerProvider/BatchSpanProcessor, and race to
        # overwrite `_provider`/`_tracer` -- the loser's provider (and its
        # background exporter thread) became unreachable for `close()` to
        # ever shut down. FastAPI's synchronous route handlers genuinely
        # run concurrently in worker threads (api/__init__.py's own
        # `_DEFAULT_MAX_CONCURRENT_REQUESTS` comment already documents
        # this), so this was a reachable production race, not a
        # theoretical one.
        self._build_lock = threading.Lock()

    def name(self) -> str:
        return "otel"

    def close(self) -> None:
        """Flush and shut down the underlying `TracerProvider`, if one was
        ever built. Called generically by `Container.close()` (which calls
        `.close()` on every registered component that has one) — without
        this, a pending `BatchSpanProcessor` batch could be silently lost on
        process exit rather than exported."""
        if self._provider is not None:
            self._provider.shutdown()

    def _get_tracer(self) -> Any:
        """Single-flight, thread-safe lazy build (double-checked locking):
        the fast path (already built) takes no lock at all; only the first
        caller(s) racing to build pay the lock's cost, and only one of them
        actually calls `_build_tracer()` -- every other concurrent caller
        blocks on the lock, then sees `self._tracer` already set by the
        winner and returns it directly, never building a second, orphaned
        `TracerProvider`."""
        if self._tracer is None:
            with self._build_lock:
                if self._tracer is None:
                    self._tracer = self._build_tracer()
        return self._tracer

    def _build_tracer(self) -> Any:
        try:
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource
            from opentelemetry.sdk.trace import TracerProvider
        except ImportError as exc:
            raise ConfigurationError(
                "OtelTracer requires the 'v4' optional dependency group "
                "(pip install modular-rag[v4]) — opentelemetry-sdk is not installed."
            ) from exc

        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: self.service_name}))
        if self.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=self.otlp_endpoint, insecure=self.otlp_insecure)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        if self.console_export:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        self._provider = provider
        return provider.get_tracer(self.service_name)

    def start_span(self, name: str, attributes: dict[str, AttributeValue] | None = None) -> _OtelSpan:
        tracer = self._get_tracer()
        # `record_exception`/`set_status_on_exception` default to True in the
        # OpenTelemetry SDK, which would embed the raw exception object
        # (`str(exc_val)`, exception args) into the span — exactly the raw,
        # potentially-PII-carrying text ADR-0012 §9 forbids. Disabled here so
        # only `_OtelSpan.__exit__`'s own safe, type-name-only recording ever
        # reaches the span.
        span_cm = tracer.start_as_current_span(
            name,
            attributes=attributes or {},
            record_exception=False,
            set_status_on_exception=False,
        )
        return _OtelSpan(span_cm)

    @classmethod
    def for_testing(cls, service_name: str = "modular-rag-test") -> tuple[OtelTracer, Any]:
        """Build an `OtelTracer` wired to an in-process `InMemorySpanExporter`
        instead of OTLP — this is the "test using an in-memory exporter"
        requirement. `SimpleSpanProcessor` exports synchronously (unlike the
        real `BatchSpanProcessor`), so a test can assert on finished spans
        immediately after the `with` block exits, with no sleep/poll needed.

        Returns `(tracer, exporter)` — call `exporter.get_finished_spans()`
        to inspect what was recorded.
        """
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        tracer = cls(service_name=service_name)
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer._provider = provider
        tracer._tracer = provider.get_tracer(service_name)
        return tracer, exporter
