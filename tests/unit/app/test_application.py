from modular_rag.app.application import ApplicationService
from modular_rag.contracts.engine import EngineRequest, EngineResult, ExecutionContext


class _Native:
    manifest_id = "test"

    def __init__(self, *, tenant_policy_active: bool = False) -> None:
        self.closed = False
        self.tenant_policy_active = tenant_policy_active

    def close(self) -> None:
        self.closed = True


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
