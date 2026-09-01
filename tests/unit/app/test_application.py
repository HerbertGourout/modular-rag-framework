from typing import Any

import pytest

from modular_rag.app.application import ApplicationService
from modular_rag.contracts.engine import EngineRequest, EngineResult, ExecutionContext
from modular_rag.contracts.feedback import FeedbackRating
from modular_rag.core.errors import ConfigurationError, SecurityError
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieval_result import RetrievalResult
from modular_rag.core.models.retrieved import RetrievedChunk


class _Native:
    manifest_id = "test"

    def __init__(
        self,
        *,
        tenant_policy_active: bool = False,
        tracer: Any | None = None,
        meter: Any | None = None,
        indexer: Any | None = None,
        feedback_sink: Any | None = None,
        review_queue: Any | None = None,
        lifecycle_ledger: Any | None = None,
        record_feedback_error: Exception | None = None,
    ) -> None:
        self.closed = False
        self.tenant_policy_active = tenant_policy_active
        self.tracer = tracer
        self.meter = meter
        self.indexer = indexer
        self.feedback_sink = feedback_sink
        self.review_queue = review_queue
        self.lifecycle_ledger = lifecycle_ledger
        self.last_retrieve_question: str | None = None
        self.retrieve_error: Exception | None = None
        self.recorded_feedback: list[Any] = []
        self._record_feedback_error = record_feedback_error

    def close(self) -> None:
        self.closed = True

    def record_feedback(self, feedback: Any) -> Any:
        if self._record_feedback_error is not None:
            raise self._record_feedback_error
        self.recorded_feedback.append(feedback)
        return feedback

    def retrieve(
        self, question: str, k: int = 10, tenant_id: str | None = None
    ) -> RetrievalResult:
        self.last_retrieve_question = question
        if self.retrieve_error is not None:
            raise self.retrieve_error
        chunk = Chunk(doc_id=new_id(), content=f"chunk for: {question}")
        return RetrievalResult(
            chunks=[RetrievedChunk(chunk=chunk, score=0.9, rank=1)], trace_id=new_id()
        )


class _RecordingMeter:
    """ADR-0013 — records every counter()/histogram()/gauge() call, mirroring
    `tests/unit/orchestration/test_engine.py`'s own fake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float, dict]] = []

    def counter(self, name: str, value: float = 1, attributes: dict | None = None) -> None:
        self.calls.append(("counter", name, value, attributes or {}))

    def histogram(self, name: str, value: float, attributes: dict | None = None) -> None:
        self.calls.append(("histogram", name, value, attributes or {}))

    def gauge(self, name: str, value: float, attributes: dict | None = None) -> None:
        self.calls.append(("gauge", name, value, attributes or {}))

    def name(self) -> str:
        return "recording-meter"

    def calls_named(self, metric_name: str) -> list[tuple[str, str, float, dict]]:
        return [c for c in self.calls if c[1] == metric_name]


class _Selected:
    """Captures the `ExecutionContext`/`EngineRequest` it was called with, so
    tests can assert on exactly what `ApplicationService.answer()` propagates
    downstream — this is the fake `DocumentEngine` side of the boundary the
    bug lived in (`context.tenant_id` fabricated as `"default"`)."""

    def __init__(self) -> None:
        self.received_context: ExecutionContext | None = None
        self.received_request: EngineRequest | None = None

    def name(self) -> str:
        return "selected-engine"

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        self.received_request = request
        self.received_context = context
        return EngineResult(text=f"answer to: {request.query.text}")


def test_application_exposes_selected_engine_name() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    assert service.engine_name == "selected-engine"


def test_indexer_property_delegates_to_native() -> None:
    """Codex review (pass 1, MEDIUM-002): `scripts/run_benchmark.py` needs
    `ApplicationService.indexer` to call `.clear()` before each ingest,
    same "public accessor" pattern already used for `tracer`/`meter`."""
    indexer = object()
    service = ApplicationService(_Native(indexer=indexer), _Selected())  # type: ignore[arg-type]

    assert service.indexer is indexer


def test_feedback_sink_review_queue_and_lifecycle_ledger_properties_delegate_to_native() -> None:
    """Same "public accessor" pattern as `indexer` above, added for
    `scripts/run_drift_check.py` (Batch 14)."""
    feedback_sink, review_queue, lifecycle_ledger = object(), object(), object()
    service = ApplicationService(
        _Native(
            feedback_sink=feedback_sink,
            review_queue=review_queue,
            lifecycle_ledger=lifecycle_ledger,
        ),
        _Selected(),  # type: ignore[arg-type]
    )

    assert service.feedback_sink is feedback_sink
    assert service.review_queue is review_queue
    assert service.lifecycle_ledger is lifecycle_ledger


# ---------------------------------------------------------------------------
# Batch 14 (ADR-0014): ApplicationService.record_feedback().
# ---------------------------------------------------------------------------


def test_record_feedback_delegates_to_native_and_returns_the_feedback() -> None:
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    result = service.record_feedback(
        "trace-1", idempotency_key="k1", rating=FeedbackRating.THUMBS_UP
    )

    assert len(native.recorded_feedback) == 1
    assert native.recorded_feedback[0] is result
    assert result.trace_id == "trace-1"
    assert result.idempotency_key == "k1"
    assert result.rating == FeedbackRating.THUMBS_UP


def test_record_feedback_returns_what_native_actually_stored_not_the_local_object() -> None:
    """`RAGEngine.record_feedback()` may redact `correction_text` before
    storing — `ApplicationService.record_feedback()` must return that
    stored record, not the pre-redaction object it built locally (pass 1
    security review finding)."""
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    def _redact_and_store(feedback: Any) -> Any:
        redacted = feedback.model_copy(update={"correction_text": "[REDACTED]"})
        native.recorded_feedback.append(redacted)
        return redacted

    native.record_feedback = _redact_and_store  # type: ignore[method-assign]

    result = service.record_feedback(
        "trace-1", idempotency_key="k1", correction_text="alice@example.com"
    )

    assert result.correction_text == "[REDACTED]"


def test_record_feedback_propagates_a_configuration_error_from_native() -> None:
    native = _Native(record_feedback_error=ConfigurationError("no feedback_sink"))
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    with pytest.raises(ConfigurationError):
        service.record_feedback("trace-1", idempotency_key="k1")


def test_record_feedback_rejects_is_test_without_the_tester_role() -> None:
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    with pytest.raises(SecurityError, match="tester"):
        service.record_feedback(
            "trace-1", idempotency_key="k1", is_test=True, roles=frozenset()
        )
    assert native.recorded_feedback == []  # never reached the native engine


def test_record_feedback_allows_is_test_with_the_tester_role() -> None:
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    result = service.record_feedback(
        "trace-1", idempotency_key="k1", is_test=True, roles=frozenset({"tester"})
    )

    assert result.is_test is True
    assert len(native.recorded_feedback) == 1


def test_application_closes_native_container_resources() -> None:
    native = _Native()
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    service.close()

    assert native.closed is True


# ---------------------------------------------------------------------------
# Lot 1 — tenant fail-closed: regression tests for the `tenant_id or "default"`
# fabrication bug. `test_answer_passes_none_tenant_to_execution_context_when_
# unauthenticated` reproduces the bug (must fail against the pre-fix code:
# `context.tenant_id` was `"default"`, not `None`); the rest lock the fixed
# behavior in place.
# ---------------------------------------------------------------------------


def test_answer_passes_none_tenant_to_execution_context_when_unauthenticated() -> None:
    """No identity supplied (no tenant_id) must reach `ExecutionContext` as
    `None`, never as a fabricated `"default"` string — fabricating a value
    here is what let an unauthenticated caller sail past
    `TenantIsolationPolicy.enforce_query()`'s `if not query.tenant_id: raise`
    check downstream, since `"default"` is truthy."""
    selected = _Selected()
    service = ApplicationService(_Native(), selected)  # type: ignore[arg-type]

    service.answer("What is RAG?")

    assert selected.received_context is not None
    assert selected.received_context.tenant_id is None


def test_answer_passes_authenticated_tenant_id_through_unchanged() -> None:
    selected = _Selected()
    service = ApplicationService(_Native(), selected)  # type: ignore[arg-type]

    service.answer("What is RAG?", tenant_id="acme-corp")

    assert selected.received_context is not None
    assert selected.received_context.tenant_id == "acme-corp"


def test_answer_does_not_set_a_tenant_id_on_the_query_either() -> None:
    """The `Query` passed inside `EngineRequest` must carry the same real
    (possibly `None`) tenant_id as `ExecutionContext` — no fabrication on
    either side of the boundary."""
    selected = _Selected()
    service = ApplicationService(_Native(), selected)  # type: ignore[arg-type]

    service.answer("What is RAG?")

    assert selected.received_request is not None
    assert selected.received_request.query.tenant_id is None


def test_answer_propagates_user_id_and_roles_into_execution_context() -> None:
    selected = _Selected()
    service = ApplicationService(_Native(), selected)  # type: ignore[arg-type]

    service.answer(
        "What is RAG?",
        tenant_id="acme-corp",
        user_id="u1",
        roles=frozenset({"admin"}),
    )

    assert selected.received_context is not None
    assert selected.received_context.user_id == "u1"
    assert selected.received_context.roles == frozenset({"admin"})


def test_answer_defaults_user_id_and_roles_when_unauthenticated() -> None:
    selected = _Selected()
    service = ApplicationService(_Native(), selected)  # type: ignore[arg-type]

    service.answer("What is RAG?")

    assert selected.received_context is not None
    assert selected.received_context.user_id is None
    assert selected.received_context.roles == frozenset()


def test_requires_identity_is_false_when_native_has_no_tenant_policy() -> None:
    service = ApplicationService(_Native(tenant_policy_active=False), _Selected())  # type: ignore[arg-type]

    assert service.requires_identity is False


def test_requires_identity_is_true_when_native_has_a_tenant_policy() -> None:
    service = ApplicationService(_Native(tenant_policy_active=True), _Selected())  # type: ignore[arg-type]

    assert service.requires_identity is True


# ---------------------------------------------------------------------------
# ADR-0012 — OpenTelemetry tracing (Lot 11, external plan; not this repo's
# own docs/refactoring-plan.md Lot 11a/b/c sequence).
# ---------------------------------------------------------------------------


def test_tracer_property_delegates_to_native() -> None:
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, _exporter = OtelTracer.for_testing()
    service = ApplicationService(_Native(tracer=tracer), _Selected())  # type: ignore[arg-type]

    assert service.tracer is tracer


def test_tracer_property_is_none_when_native_has_none() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    assert service.tracer is None


def test_answer_with_no_tracer_configured_does_not_raise() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    answer = service.answer("What is RAG?")

    assert answer.text == "answer to: What is RAG?"


def test_answer_creates_a_root_span_carrying_correlation_and_request_id() -> None:
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, exporter = OtelTracer.for_testing()
    service = ApplicationService(_Native(tracer=tracer), _Selected())  # type: ignore[arg-type]

    service.answer("What is RAG?")

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["app.request"]
    span = spans[0]
    assert span.attributes["correlation_id"]
    assert span.attributes["request_id"]
    assert span.attributes["engine"] == "selected-engine"
    assert span.attributes["status"] == "ok"
    # No query text ever appears as a span attribute value.
    for value in span.attributes.values():
        assert "What is RAG?" not in str(value)


class _FailingSelected:
    def name(self) -> str:
        return "selected-engine"

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        raise RuntimeError("downstream engine failed, should never appear in the span")


def test_answer_records_error_on_span_when_the_engine_raises() -> None:
    import pytest

    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, exporter = OtelTracer.for_testing()
    service = ApplicationService(_Native(tracer=tracer), _FailingSelected())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="downstream engine failed"):
        service.answer("What is RAG?")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
    assert spans[0].status.description == "RuntimeError"
    assert "downstream engine failed" not in (spans[0].status.description or "")


# ---------------------------------------------------------------------------
# Codex review pass 1, HIGH-002: `retrieve()` previously propagated no
# correlation_id/request_id and created no application-layer span at all,
# unlike `answer()`. These tests lock in the fix.
# ---------------------------------------------------------------------------


def test_retrieve_with_no_tracer_configured_does_not_raise() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    result = service.retrieve("What is RAG?")

    assert len(result.chunks) == 1
    assert result.trace_id


def test_retrieve_creates_a_root_span_carrying_correlation_request_and_trace_id() -> None:
    """Codex review pass 2 (HIGH-002, reopened): a previous version of this
    test locked in the *absence* of `app.trace_id` -- codifying an
    unauthorized narrowing of the original acceptance criterion. Per an
    explicit human decision, `RAGEngine.retrieve()` now builds a real
    `Trace` and `app.trace_id` is present, matching `RetrievalResult.trace_id`."""
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, exporter = OtelTracer.for_testing()
    service = ApplicationService(_Native(tracer=tracer), _Selected())  # type: ignore[arg-type]

    result = service.retrieve("What is RAG?")

    spans = exporter.get_finished_spans()
    assert [s.name for s in spans] == ["app.request"]
    span = spans[0]
    assert span.attributes["correlation_id"]
    assert span.attributes["request_id"]
    assert span.attributes["operation"] == "retrieve"
    assert span.attributes["status"] == "ok"
    # No "engine" attribute -- retrieve() never dispatches through a
    # DocumentEngine, unlike answer().
    assert "engine" not in span.attributes
    assert span.attributes["app.trace_id"] == result.trace_id
    for value in span.attributes.values():
        assert "What is RAG?" not in str(value)


def test_retrieve_and_answer_use_distinct_correlation_and_request_ids() -> None:
    """Each call gets its own fresh identifiers -- they must never be
    accidentally shared/cached across calls."""
    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, exporter = OtelTracer.for_testing()
    service = ApplicationService(_Native(tracer=tracer), _Selected())  # type: ignore[arg-type]

    service.answer("What is RAG?")
    service.retrieve("What is RAG?")

    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert spans[0].attributes["correlation_id"] != spans[1].attributes["correlation_id"]
    assert spans[0].attributes["request_id"] != spans[1].attributes["request_id"]


def test_retrieve_records_error_on_span_without_raw_exception_text() -> None:
    import pytest

    from modular_rag.adapters.observability.otel_tracing import OtelTracer

    tracer, exporter = OtelTracer.for_testing()
    native = _Native(tracer=tracer)
    native.retrieve_error = RuntimeError("db password is hunter2")
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="db password"):
        service.retrieve("What is RAG?")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code.name == "ERROR"
    assert spans[0].status.description == "RuntimeError"
    assert "hunter2" not in (spans[0].status.description or "")


# ---------------------------------------------------------------------------
# ADR-0013 (Lot 12, external plan): `mrag.request.duration_ms`/
# `mrag.request.errors` are recorded here (ApplicationService), not inside
# `RAGEngine._run()`/`.retrieve()` -- deliberately, so a native-engine
# request is counted exactly once (not twice) and a LangGraph-routed request
# (which never reaches `RAGEngine` at all) is still counted, since this
# boundary is engine-neutral.
# ---------------------------------------------------------------------------


def test_answer_with_no_meter_configured_does_not_raise() -> None:
    service = ApplicationService(_Native(), _Selected())  # type: ignore[arg-type]

    service.answer("What is RAG?")


def test_answer_emits_a_duration_histogram_with_operation_engine_and_status() -> None:
    meter = _RecordingMeter()
    service = ApplicationService(_Native(meter=meter), _Selected())  # type: ignore[arg-type]

    service.answer("What is RAG?")

    call = meter.calls_named("mrag.request.duration_ms")[0]
    assert call[0] == "histogram"
    assert call[3] == {"operation": "answer", "engine": "selected-engine", "status": "ok"}


def test_answer_emits_an_errors_counter_with_status_error_and_no_duration_status_ok() -> None:
    import pytest

    meter = _RecordingMeter()
    service = ApplicationService(_Native(meter=meter), _FailingSelected())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        service.answer("What is RAG?")

    duration_call = meter.calls_named("mrag.request.duration_ms")[0]
    assert duration_call[3]["status"] == "error"
    error_call = meter.calls_named("mrag.request.errors")[0]
    assert error_call[3] == {
        "operation": "answer",
        "engine": "selected-engine",
        "error_type": "RuntimeError",
    }


def test_retrieve_emits_a_duration_histogram_with_native_engine_label() -> None:
    meter = _RecordingMeter()
    service = ApplicationService(_Native(meter=meter), _Selected())  # type: ignore[arg-type]

    service.retrieve("What is RAG?")

    call = meter.calls_named("mrag.request.duration_ms")[0]
    assert call[3] == {"operation": "retrieve", "engine": "native", "status": "ok"}


def test_retrieve_emits_an_errors_counter_on_failure() -> None:
    import pytest

    meter = _RecordingMeter()
    native = _Native(meter=meter)
    native.retrieve_error = RuntimeError("db password is hunter2")
    service = ApplicationService(native, _Selected())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        service.retrieve("What is RAG?")

    call = meter.calls_named("mrag.request.errors")[0]
    assert call[3] == {"operation": "retrieve", "engine": "native", "error_type": "RuntimeError"}
    # PII safety: the exception message itself must never reach a label value.
    assert "hunter2" not in str(call[3])
