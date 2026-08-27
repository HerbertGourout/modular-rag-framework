from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.contracts.tracing import AttributeValue

_SafeAttributes = dict[str, AttributeValue]


@runtime_checkable
class Meter(Protocol):
    """Live operational metrics — counters, histograms, gauges (ADR-0013).

    **Distinct from `core.models.metrics.Metrics`**, a post-hoc, per-run
    evaluation-quality bag (recall/precision/groundedness/etc, scored offline
    or via `Telemetry.record_metrics()`). `Meter` is the operational-SRE
    counterpart: request rate, error rate, latency distribution, token/cost
    counters, degraded-mode and rejection signals — the continuously-sampled,
    dashboard-and-alert-facing kind of metric, not a single run's quality
    score. The two mechanisms are deliberately independent; a pipeline may
    configure either, both, or neither.

    **Responsibility:**
    - Record a counter increment, a histogram observation, or a gauge value,
      each tagged with a small, bounded set of *label* attributes.
    - Be safe to call unconditionally when disabled (`NullMeter`) or when the
      configured export target is unavailable (`OtelMeter` — export failures
      must never surface as an exception from any of these methods).
    - Guard against unbounded label cardinality: an implementation must never
      let a caller's attribute value explode the number of distinct time
      series a metrics backend has to track (see `OtelMeter`'s
      `_sanitize_attributes()` for the concrete allowlist/pattern check this
      Protocol's real implementation applies as defense in depth).

    **NOT Responsible for:**
    - Recording a live distributed-trace span — that is `Tracer`'s job
      (`contracts/tracing.py`, ADR-0012), a deliberately separate mechanism.
    - Deciding *which* attribute values are safe as labels — callers must
      never pass a per-request identifier (`correlation_id`, `request_id`,
      `trace_id`, `query_id`, `chunk_id`, `document_id`/`doc_id`) as a label
      value; only small, enumerable categories (an operation name, a bounded
      status/stage/source string, a known model identifier) belong as labels.
      Unlike a span attribute (unbounded cardinality is fine — one value per
      span, discarded after export), a metric *label* creates one persistent
      time series per distinct value combination in the backend, so an
      unbounded value here is a real production incident waiting to happen,
      not just a style nit.

    **Usage:**
    Registered on `Container.meter` (optional — `None` when no meter is
    configured; every call site must guard with `if self._c.meter:`, matching
    every other optional `Container` role). Selected in a manifest under
    `observability.meter`.

    **Example** (real API):
    ```python
    container = create_default_registry().wire(manifest)
    if container.meter:
        container.meter.counter("mrag.request.errors", attributes={"operation": "answer"})
        container.meter.histogram("mrag.request.duration_ms", 42.5, attributes={"operation": "answer"})
        container.meter.gauge("mrag.review.pending", 3.0)
    ```

    **Errors:**
    - Must not raise for a normal `counter()`/`histogram()`/`gauge()` call,
      even when the underlying export backend is unreachable — the caller's
      business logic must never fail because metrics emission failed.
    """

    def counter(
        self, name: str, value: int | float = 1, attributes: _SafeAttributes | None = None
    ) -> None:
        """Increment a counter (a monotonically increasing total — request
        counts, error counts, token counts, cost accumulation).

        Args:
            name: A stable, dotted metric name (e.g. `"mrag.request.errors"`).
            value: The amount to add (default `1` for a simple event count).
            attributes: Safe, bounded-cardinality label attributes.
        """
        ...

    def histogram(
        self, name: str, value: float, attributes: _SafeAttributes | None = None
    ) -> None:
        """Record one observation into a histogram (latency distributions,
        chunk counts per request — anything a p50/p95/p99 is meaningful for).

        Args:
            name: A stable, dotted metric name (e.g. `"mrag.request.duration_ms"`).
            value: The observed value (e.g. a latency in milliseconds).
            attributes: Safe, bounded-cardinality label attributes.
        """
        ...

    def gauge(self, name: str, value: float, attributes: _SafeAttributes | None = None) -> None:
        """Set a gauge to its current value (point-in-time state — readiness
        state, pending review-queue depth, reconciliation divergence count —
        anything that goes up *and* down, unlike a counter).

        Args:
            name: A stable, dotted metric name (e.g. `"mrag.review.pending"`).
            value: The current value.
            attributes: Safe, bounded-cardinality label attributes.
        """
        ...

    def name(self) -> str:
        """Return the component's identifier (e.g. `"otel"`, `"null"`)."""
        ...
