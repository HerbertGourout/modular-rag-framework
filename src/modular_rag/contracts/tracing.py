from __future__ import annotations

from typing import Protocol, runtime_checkable

AttributeValue = str | int | float | bool

_SafeAttributes = dict[str, AttributeValue]


@runtime_checkable
class Span(Protocol):
    """One live span in a distributed trace (ADR-0012).

    **Responsibility:**
    - Accept safe (non-PII) attributes describing the operation it wraps
    - Record that the operation failed, without capturing raw exception text
      that might embed sensitive request/response content
    - Be usable as a context manager: entering starts the span, exiting ends it

    **NOT Responsible for:**
    - Deciding *what* is safe to attach — callers must never pass query text,
      document content, answer text, or token content as an attribute value.
    - Exporting itself anywhere — that is the owning `Tracer`'s responsibility.

    **Usage:**
    Obtained from `Tracer.start_span()`. Never constructed directly.

    **Example:**
    ```python
    with tracer.start_span("rag.retrieve", attributes={"chunks_requested": k}) as span:
        chunks = retriever.retrieve(query, k=k)
        span.set_attribute("chunks_returned", len(chunks))
    ```
    """

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        """Attach one safe, non-PII attribute to the span."""
        ...

    def record_error(self, message: str) -> None:
        """Mark the span as failed. `message` must be a short, safe
        classification (e.g. an exception type name) — never raw exception
        text that might embed request/response content."""
        ...

    def __enter__(self) -> Span: ...

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    """Create live spans for a distributed trace (ADR-0012).

    **Responsibility:**
    - Start a new span, nested under whatever span is currently active in the
      same call stack (parent/child nesting is the implementation's concern —
      see `OtelTracer`, which delegates this to OpenTelemetry's own context
      propagation rather than tracking parents itself)
    - Be safe to call unconditionally when disabled (`NullTracer`) or when the
      configured export target is unavailable (`OtelTracer` — export failures
      must never surface as an exception from `start_span()` or from the
      returned `Span`'s context-manager methods)

    **NOT Responsible for:**
    - Recording a post-hoc `Trace`/aggregate `Metrics` — that is `Telemetry`'s
      job (`contracts/telemetry.py`), a deliberately separate mechanism.
    - Deciding whether a given pipeline stage should be traced — callers
      (`orchestration/`, `app/`, `api/`) decide where to call `start_span()`.

    **Usage:**
    Registered on `Container.tracer` (optional — `None` when no tracer is
    configured; every call site must guard with `if self._c.tracer:`, matching
    every other optional `Container` role). Selected in a manifest under
    `observability.tracer`.

    **Example** (real API):
    ```python
    container = create_default_registry().wire(manifest)
    if container.tracer:
        with container.tracer.start_span("rag.answer") as span:
            ...
    ```

    **Errors:**
    - Must not raise for a normal `start_span()` call, even when the
      underlying export backend is unreachable — the caller's business logic
      must never fail because tracing failed.
    """

    def start_span(self, name: str, attributes: _SafeAttributes | None = None) -> Span:
        """Start (and, via the returned context manager, later end) one span.

        Args:
            name: A short, stable operation name (e.g. `"rag.retrieve"`).
            attributes: Safe, non-PII attributes known at start time. More may
                be added later via `Span.set_attribute()`.
        """
        ...

    def name(self) -> str:
        """Return the component's identifier (e.g. `"otel"`, `"null"`)."""
        ...
