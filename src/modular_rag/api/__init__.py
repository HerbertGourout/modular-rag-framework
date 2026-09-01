from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from modular_rag import __version__
from modular_rag.api.errors import to_http_exception
from modular_rag.api.middleware import (
    ConcurrencyLimitMiddleware,
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    TracingMiddleware,
)
from modular_rag.app.public import (
    AuthenticationError,
    ConfigurationError,
    FeedbackRating,
    ReadinessState,
    TenantContext,
    TokenVerifier,
)
from modular_rag.app.public import (
    load_application as load_pipeline,
)

_DEFAULT_MAX_BODY_BYTES = 1_000_000  # 1 MB
_DEFAULT_RATE_LIMIT_PER_MINUTE = 60
# All routes here are `def`, not `async def`, so Starlette runs them via
# `anyio.to_thread.run_sync`, whose default capacity limiter caps concurrent
# threads at 40 — a `max_concurrent` above that would never actually be the
# binding constraint (orchestration-specialist review, Lot 6): requests
# beyond the 40th would queue inside anyio instead of getting the intended
# fast 503 here. Kept safely below that ceiling rather than reconfiguring
# anyio's global thread limiter, which is a bigger, riskier change than this
# Lot's "add concurrency limits" scope calls for.
_DEFAULT_MAX_CONCURRENT_REQUESTS = 30


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    text: str
    citations: list[dict[str, object]]
    trace_id: str | None = None


class FeedbackRequest(BaseModel):
    """ADR-0014 (Batch 14). `trace_id` is required — the only identifier
    this API returns to a caller (`AnswerResponse.trace_id`), so it is the
    only way to link feedback back to an answer. `idempotency_key` is
    required: a retried submission with the same key is a silent no-op, not
    an error — clients should generate one per logical feedback action
    (e.g. once per thumbs-up click), not per HTTP retry attempt."""

    trace_id: str
    rating: FeedbackRating | None = None
    correction_text: str | None = None
    citation_count: int | None = None
    idempotency_key: str
    is_test: bool = False


class FeedbackResponse(BaseModel):
    id: str


class RetrieveResponse(BaseModel):
    """ADR-0012, Codex review pass 2 HIGH-002: `/retrieve` used to return a
    bare JSON array of chunks with no trace_id anywhere in the response —
    changed to an object so a caller can correlate a retrieval call with its
    trace, the same way `AnswerResponse.trace_id` already lets them do for
    `/answer`. A genuine breaking response-shape change (array -> object);
    acceptable pre-launch per the project's own pre-alpha status."""

    chunks: list[dict[str, object]]
    trace_id: str


def create_app(
    manifest_path: str,
    *,
    token_verifier: TokenVerifier | None = None,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    rate_limit_per_minute: int = _DEFAULT_RATE_LIMIT_PER_MINUTE,
    max_concurrent_requests: int = _DEFAULT_MAX_CONCURRENT_REQUESTS,
) -> FastAPI:
    """Factory: load a pipeline from a manifest and expose it as a FastAPI app.

    `QuestionRequest`/`AnswerResponse` are module-level, not nested inside this
    function, on purpose (Lot 8, docs/refactoring-plan.md): with
    `from __future__ import annotations`, a locally-scoped class produces an
    unresolvable forward-reference annotation that FastAPI silently
    misinterprets as a query parameter instead of a request body — this is
    what made `POST /answer` return 422 on every documented call before this
    fix. See tests/unit/api/test_api.py for the regression test.

    `token_verifier` (Lot 16a, docs/refactoring-plan.md — closes the residual
    gap Lot 11b recorded: "no API/CLI authentication middleware calls the
    verifier yet"): when given, `/answer` and `/retrieve` require a valid
    `Authorization: Bearer <token>` header, verified through it; the resulting
    `TenantContext.tenant_id` is threaded into the pipeline call so
    `Container.tenant_policy` (if configured) enforces/filters by the
    *authenticated* tenant, never a caller-supplied one — there is no request
    field a caller can set to claim a tenant identity.

    `None` (the default) leaves every route open **only for a manifest with
    no `tenant_policy` wired** — unauthenticated local/dev use, matching
    every other optional-component precedent in this codebase (guard,
    redactor, tenant_policy itself). A manifest that *does* wire a
    `tenant_policy` (Codex review finding, Lot 1 follow-up: this is exactly
    what `governance.tenant_enforcement` is supposed to gate, but
    `registry.py::wire()` wires `tenant_policy` on presence alone,
    independent of that flag — see `validate_capabilities()`'s matching
    rejection of the inverse contradiction) makes `token_verifier` effectively
    mandatory: `create_app()` raises `ConfigurationError` at startup rather
    than silently leaving routes open against a tenant-isolated pipeline —
    see below. Any deployment serving more than one tenant's data must
    configure a verifier (`adapters.auth.keycloak_verifier.KeycloakTokenVerifier`
    is the reference implementation, Lot 11b) *before* selecting a
    tenant-isolated manifest, or the service will refuse to start — not fail
    per-request at 401/403 after deployment.

    Raises `ConfigurationError` immediately (before the FastAPI app is even
    constructed) if the loaded pipeline has a `tenant_policy` wired
    (`pipeline.requires_identity` — true whenever `governance.tenant_policy`
    is set, *regardless* of `governance.tenant_enforcement`'s value, because
    `RAGEngine`/`LangGraphEngineAdapter` both gate enforcement on the
    former's presence, not the latter's flag; see
    `RAGEngine.tenant_policy_active`) but no `token_verifier` was given
    (Lot 1, tenant fail-closed): without this check, `token_verifier=None`
    would leave `_authenticate()` always returning `identity=None`, and a
    request with no tenant_id anywhere would only be caught downstream by
    `TenantIsolationPolicy` — as a 403 on every single request, a confusing
    silent misconfiguration rather than a clear refusal to start. Failing at
    startup instead matches `validate_capabilities()`'s existing precedent
    for a declared-but-not-activatable manifest section (ADR-0007 §3: "a
    declared manifest section that cannot be activated must fail
    validation").
    """
    pipeline = load_pipeline(manifest_path)
    if pipeline.requires_identity and token_verifier is None:
        raise ConfigurationError(
            f"Manifest {manifest_path!r} has a tenant_policy wired "
            "(governance.tenant_policy) but create_app() was not given a "
            "token_verifier. Refusing to start an API that would silently serve a "
            "tenant-isolated pipeline to unauthenticated callers — pass "
            "token_verifier=... (e.g. KeycloakTokenVerifier) to create_app()."
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            close = getattr(pipeline, "close", None)
            if close is not None:
                close()

    api = FastAPI(
        title="Modular RAG API",
        version=__version__,
        description="Production-grade RAG and agentic reasoning API.",
        lifespan=lifespan,
    )
    api.add_middleware(RateLimitMiddleware, requests_per_minute=rate_limit_per_minute)
    api.add_middleware(MaxBodySizeMiddleware, max_bytes=max_body_bytes)
    api.add_middleware(ConcurrencyLimitMiddleware, max_concurrent=max_concurrent_requests)
    api.add_middleware(TracingMiddleware, tracer=pipeline.tracer)

    _bearer = HTTPBearer(auto_error=False)

    def _authenticate(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
    ) -> TenantContext | None:
        if token_verifier is None:
            return None
        if credentials is None:
            raise HTTPException(status_code=401, detail="Missing bearer token.")
        try:
            return token_verifier.verify(credentials.credentials)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @api.get("/health")
    def health() -> dict[str, str]:
        """Liveness: the process is up and the pipeline is wired. Never
        requires auth — this is what an orchestrator's own probe hits."""
        return {"status": "ok", "pipeline": pipeline.manifest_id}

    @api.get("/ready")
    def ready(response: Response) -> dict[str, object]:
        """Readiness (Lot 16a stub replaced by Lot 6 — readiness and
        resilience): actually probes the wired pipeline's external
        dependencies (Qdrant, PostgreSQL when a manifest configures them,
        and — since Codex review HIGH-001, ADR-0010's fourth pass — the
        configured LLM generator too, via a real, cached, credential-
        validating call) via `pipeline.check_readiness()`, instead of only
        confirming `create_app()` finished wiring (that's still all
        `/health` above checks — pure liveness). See
        `orchestration.container.Container.check_readiness()`'s own
        docstring for exactly which registered roles are probed and which
        are treated as critical (`generator` always is — see
        `_CRITICAL_ROLES`) — a manifest requiring a real LLM credential
        will report `unready` until one is actually configured, which is
        the intended, honest behavior this endpoint exists to provide, not
        a defect.

        HTTP 503 only for `unready` — `degraded` still returns 200 so an
        orchestrator keeps the pod in rotation, just visibly flagged, per
        `core.enums.ReadinessState`'s own docstring on the distinction.

        ADR-0013 ("degraded modes"): when a meter is configured, also
        records `mrag.readiness.state` — a gauge, one call per `/ready` poll,
        labeled by the current `state` (a fixed 3-value set:
        `healthy`/`degraded`/`unready`). This is the *static, whole-process*
        degradation signal; `mrag.retrieve.degraded` (recorded in
        `orchestration/engine.py`) is the complementary *per-request* signal
        — see ADR-0013's own note on why these are deliberately two separate
        metrics, not one.
        """
        report = pipeline.check_readiness()
        if report.status == ReadinessState.UNREADY:
            response.status_code = 503
        if pipeline.meter is not None:
            pipeline.meter.gauge("mrag.readiness.state", 1, attributes={"state": report.status.value})
        return {
            "status": report.status.value,
            "pipeline": pipeline.manifest_id,
            "dependencies": [d.model_dump() for d in report.dependencies],
        }

    @api.post("/answer", response_model=AnswerResponse)
    def answer(
        req: QuestionRequest,
        identity: TenantContext | None = Depends(_authenticate),  # noqa: B008
    ) -> AnswerResponse:
        try:
            ans = pipeline.answer(
                req.question,
                tenant_id=identity.tenant_id if identity else None,
                user_id=identity.user_id if identity else None,
                roles=identity.roles if identity else frozenset(),
            )
        except Exception as exc:
            raise to_http_exception(exc) from exc
        return AnswerResponse(
            text=ans.text,
            citations=[c.model_dump() for c in ans.citations],
            trace_id=ans.trace_id,
        )

    @api.post("/feedback", response_model=FeedbackResponse)
    def feedback(
        req: FeedbackRequest,
        identity: TenantContext | None = Depends(_authenticate),  # noqa: B008
    ) -> FeedbackResponse:
        """Record user feedback on a previously returned answer (Batch 14,
        ADR-0014). Requires the same authentication as `/answer`/`/retrieve`
        when a `token_verifier` is configured. `Feedback.correction_text` is
        rejected with a mapped error unless the wired pipeline has a
        `governance.redactor` configured (the explicit sensitive-content
        policy `RAGEngine.record_feedback()` enforces) — see
        `docs/guides/feedback-and-drift.md`.
        """
        try:
            result = pipeline.record_feedback(
                req.trace_id,
                tenant_id=identity.tenant_id if identity else None,
                user_id=identity.user_id if identity else None,
                roles=identity.roles if identity else frozenset(),
                rating=req.rating,
                correction_text=req.correction_text,
                citation_count=req.citation_count,
                idempotency_key=req.idempotency_key,
                is_test=req.is_test,
            )
        except Exception as exc:
            raise to_http_exception(exc) from exc
        return FeedbackResponse(id=result.id)

    @api.get("/retrieve", response_model=RetrieveResponse)
    def retrieve(
        q: str,
        k: int = 10,
        identity: TenantContext | None = Depends(_authenticate),  # noqa: B008
    ) -> RetrieveResponse:
        try:
            result = pipeline.retrieve(
                q, k=k, tenant_id=identity.tenant_id if identity else None
            )
        except Exception as exc:
            raise to_http_exception(exc) from exc
        return RetrieveResponse(
            chunks=[
                {"chunk_id": rc.chunk.id, "score": rc.score, "content": rc.chunk.content[:300]}
                for rc in result.chunks
            ],
            trace_id=result.trace_id,
        )

    return api
