"""Existing-application adapter for a hook-exposing graph application (Lot 22, ADR-0018).

Implements `DocumentEngine` and `ApplicationProfileProvider` over an application
the framework does not own. The application keeps its graph, state, prompts and
deployment; this adapter owns only the call itself and whatever hooks the
application chose to expose, and it reports the assurance those hooks genuinely
support — a ceiling (ADR-0018 §6), never a promise.

Control placement:

- request admission and result admission run in the adapter, before and after the
  application, so they exist by construction;
- retrieval-result and pre-model-egress controls attach only through the hooks
  named by `ApplicationHandle.hook_surface`. A hook the application swallows
  errors from is `OBSERVED`, one that can stop the graph is `ENFORCED`.

Identity is framework-owned (ADR-0018 §10): the tenant comes from
`ExecutionContext` alone and whatever the application returns stays inert under
`metadata["application"]`. A control that cannot answer denies (§12), and a
result is released only once the audit events it owes were persisted.

Layering: imports `contracts/` and `core/` only. The application is reached
through the structural `ApplicationHandle` below, so no vendor type appears
here; the application's own SDK is its business.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from modular_rag.contracts.application import (
    ApplicationProfile,
    ControlPoint,
    ControlPointBinding,
    ControlPointSupport,
    EgressPath,
    EgressPathKind,
    ExpectedAuditEvent,
    evidence_ceiling,
    required_audit_events,
)
from modular_rag.contracts.assurance import (
    ConformanceReport,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    classify_provenance,
    evidence_status_rank,
)
from modular_rag.contracts.audit import AuditEvent, AuditEventType, AuditSink
from modular_rag.contracts.egress import EgressOperation, EgressPolicy
from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.contracts.security import Redactor, SecurityGuard, TenantPolicy
from modular_rag.core.enums import (
    DataClassification,
    RetrievalMethod,
)
from modular_rag.core.errors import (
    EngineCapabilityError,
    PolicyViolationError,
    SecurityError,
    StorageError,
)
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk

ADAPTER_VERSION = "0.1.0"

# Attribution only: an unauthenticated request is refused, never served, but its
# refusal is still audited. This string is never read as an identity.
_UNATTRIBUTED = "unattributed"

_ENFORCEABLE_HOOKS = frozenset(
    {
        ControlPoint.RETRIEVAL_RESULT,
        ControlPoint.PRE_MODEL_EGRESS,
        ControlPoint.TOOL_INVOCATION,
        ControlPoint.STREAM_CHUNK,
    }
)


@runtime_checkable
class ApplicationHandle(Protocol):
    """What the adapter needs from a wrapped application, and nothing vendor-specific.

    `hook_surface` maps a `ControlPoint` value to whether that hook can stop the
    application (`True`) or only observes (`False`). `model_paths` maps each
    provider-reaching model call to whether it is routed through the
    `pre_model_egress` hook. `invoke` returns `{"text", "documents", "metadata"}`
    where each document is `{"id", "tenant_id", "text", "source"}`.
    """

    application_name: str
    application_version: str
    hook_surface: Mapping[str, bool]
    model_paths: Mapping[str, bool]
    tool_names: tuple[str, ...]
    streams: bool

    def invoke(
        self, text: str, tenant: str, hooks: Mapping[str, Callable[..., None]]
    ) -> dict[str, Any]: ...


class _ComponentSource(Protocol):
    """The subset of a wired `Container` this adapter reads (same local-Protocol
    technique as `LangGraphEngineAdapter`: `app/` is not importable from here)."""

    @property
    def guard(self) -> SecurityGuard | None: ...

    @property
    def tenant_policy(self) -> TenantPolicy | None: ...

    @property
    def redactor(self) -> Redactor | None: ...

    @property
    def egress_policy(self) -> EgressPolicy | None: ...

    @property
    def audit_sink(self) -> AuditSink | None: ...


class _Denied(Exception):
    """Raised inside a hook to stop the application."""


class _AuditPersistFailed(Exception):
    """The success-path audit events could not all be persisted."""


# Bounded per-request evidence, same rationale as the other engines' stores.
_EVIDENCE_CAPACITY = 32


class ExistingGraphApplicationAdapter:
    """`DocumentEngine` over a hook-exposing graph application."""

    def __init__(
        self,
        application: ApplicationHandle,
        components: _ComponentSource,
        *,
        egress_provider: str,
    ) -> None:
        unknown = {
            name for name in application.hook_surface
        } - {point.value for point in _ENFORCEABLE_HOOKS}
        if unknown:
            raise ValueError(f"not an application-owned hook: {sorted(unknown)}")
        self._app = application
        self._c = components
        self._egress_provider = egress_provider
        self._provenance: dict[str, EvidenceStatus] = {}
        self._audit_complete: dict[str, bool] = {}

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        capabilities: set[EngineCapability] = set()
        if self._app.streams:
            capabilities.add(EngineCapability.STREAMING)
        if self._app.tool_names:
            capabilities.add(EngineCapability.TOOL_USE)
        return frozenset(capabilities)

    def name(self) -> str:
        return f"existing-application:{self._app.application_name}"

    def engine_version(self) -> str:
        return ADAPTER_VERSION

    # -- profile ------------------------------------------------------------

    def _support(self, point: ControlPoint) -> ControlPointSupport:
        if point in (ControlPoint.REQUEST_ADMISSION, ControlPoint.RESULT_ADMISSION):
            return ControlPointSupport.ENFORCED
        blocking = self._app.hook_surface.get(point.value)
        if blocking is None:
            return ControlPointSupport.UNAVAILABLE
        return ControlPointSupport.ENFORCED if blocking else ControlPointSupport.OBSERVED

    def _path_is_hooked(self, name: str) -> bool:
        return (
            bool(self._app.model_paths[name])
            and ControlPoint.PRE_MODEL_EGRESS.value in self._app.hook_surface
        )

    @property
    def application_profile(self) -> ApplicationProfile:
        bindings = tuple(ControlPointBinding(p, self._support(p)) for p in ControlPoint)
        paths = tuple(
            EgressPath(
                name,
                EgressPathKind.MODEL,
                ControlPoint.PRE_MODEL_EGRESS if self._path_is_hooked(name) else None,
                self._support(ControlPoint.PRE_MODEL_EGRESS)
                if self._path_is_hooked(name)
                else ControlPointSupport.UNAVAILABLE,
            )
            for name in self._app.model_paths
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "adapter": ADAPTER_VERSION,
                    "application": [
                        self._app.application_name,
                        self._app.application_version,
                    ],
                    "hooks": sorted(self._app.hook_surface.items()),
                    "paths": sorted(self._app.model_paths.items()),
                    "egress_provider": self._egress_provider,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return ApplicationProfile(
            application_name=self._app.application_name,
            application_version=self._app.application_version,
            adapter_version=ADAPTER_VERSION,
            integration_fingerprint=f"sha256:{fingerprint}",
            bindings=bindings,
            egress_paths=paths,
            expected_audit_events=tuple(
                ExpectedAuditEvent(event, mandatory=True)
                for event in sorted(required_audit_events(bindings, paths))
            ),
        )

    # -- execution ----------------------------------------------------------

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        pending: list[tuple[AuditEventType, dict[str, Any]]] = []
        tenant = context.tenant_id

        def body() -> EngineResult:
            admitted = self._admit(request, context, pending)
            query = request.query.model_copy(update={"tenant_id": admitted})
            try:
                out = self._app.invoke(query.text, admitted, self._hooks(admitted, pending))
            except _Denied as exc:
                raise PolicyViolationError("denied by a framework control") from exc
            try:
                retrieved = [self._as_retrieved(doc) for doc in out["documents"]]
            except ValueError as exc:
                raise PolicyViolationError("unrecognised document classification") from exc
            self._admit_result(admitted, retrieved, pending)
            text = self._admit_answer(query.id, out["text"], pending)
            if self._app.model_paths:
                pending.append((AuditEventType.GENERATION_PERFORMED, {}))
            citations = self._citations(retrieved)
            self._provenance[context.request_id] = classify_provenance(citations, retrieved)
            return EngineResult(
                text=text,
                citations=citations,
                steps=[EngineStep("admission"), EngineStep("application")],
                # Application-returned identity stays inert under its own key.
                metadata={"application": dict(out.get("metadata", {}))},
            )

        return self._guarded(context, tenant, pending, body)

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        return self.run(request, context)

    async def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        raise EngineCapabilityError(f"{self.name()} does not declare streaming")
        yield  # pragma: no cover - makes this an async generator

    def _guarded(
        self,
        context: ExecutionContext,
        tenant: str | None,
        pending: list[tuple[AuditEventType, dict[str, Any]]],
        body: Callable[[], EngineResult],
    ) -> EngineResult:
        """Owns audit completion: a result is released only after every event was
        persisted, and a failed run is audited too. If its terminal event cannot
        be persisted the caller gets `StorageError`, never a quiet loss."""
        request_id = context.request_id
        pending.insert(0, (AuditEventType.QUERY_RECEIVED, {}))
        self._provenance.pop(request_id, None)
        self._audit_complete.pop(request_id, None)
        try:
            outcome = body()
            pending.append((AuditEventType.RUN_SUCCEEDED, {}))
            try:
                self._persist(context, tenant, pending)
            except Exception as persist_exc:
                raise _AuditPersistFailed from persist_exc
        except Exception as exc:
            self._provenance.pop(request_id, None)
            failed = [e for e in pending if e[0] is not AuditEventType.RUN_SUCCEEDED]
            failed.append((AuditEventType.RUN_FAILED, {}))
            lost = isinstance(exc, _AuditPersistFailed)
            for event_type, payload in failed:
                try:
                    self._record(context, tenant, event_type, payload)
                except Exception:
                    lost = True
            self._remember(self._audit_complete, request_id, not lost)
            if lost:
                raise StorageError("run audit could not be fully persisted") from exc
            raise
        self._remember(self._audit_complete, request_id, self._c.audit_sink is not None)
        return outcome

    def _persist(
        self,
        context: ExecutionContext,
        tenant: str | None,
        pending: list[tuple[AuditEventType, dict[str, Any]]],
    ) -> None:
        for event_type, payload in pending:
            self._record(context, tenant, event_type, payload)

    def _record(
        self,
        context: ExecutionContext,
        tenant: str | None,
        event_type: AuditEventType,
        payload: dict[str, Any],
    ) -> None:
        sink = self._c.audit_sink
        if sink is None:
            return
        sink.record(
            AuditEvent(
                event_type=event_type,
                correlation_id=context.correlation_id,
                tenant_id=tenant or _UNATTRIBUTED,
                actor=context.user_id,
                payload=payload,
            )
        )

    @staticmethod
    def _remember(store: dict[str, Any], key: str, value: Any) -> None:
        store[key] = value
        while len(store) > _EVIDENCE_CAPACITY:
            store.pop(next(iter(store)))

    # -- controls -----------------------------------------------------------

    def _admit(
        self,
        request: EngineRequest,
        context: ExecutionContext,
        pending: list[tuple[AuditEventType, dict[str, Any]]],
    ) -> str:
        tenant = context.tenant_id
        if not tenant:
            raise PolicyViolationError("no verified tenant context")
        query = request.query.model_copy(update={"tenant_id": tenant})
        policy = self._c.tenant_policy
        if policy is not None:
            policy.enforce_query(query)
        guard = self._c.guard
        pending.append((AuditEventType.GUARD_DECISION, {}))
        if guard is not None:
            result = guard.check_query(query)
            if not result.allowed:
                raise SecurityError(result.reason or "Query blocked by security guard.")
        return tenant

    def _hooks(
        self, tenant: str, pending: list[tuple[AuditEventType, dict[str, Any]]]
    ) -> dict[str, Callable[..., None]]:
        classifications: list[DataClassification | None] = []

        def retrieval(documents: list[dict[str, Any]]) -> None:
            pending.append((AuditEventType.RETRIEVAL_PERFORMED, {}))
            try:
                retrieved = [self._as_retrieved(doc) for doc in documents]
            except ValueError:
                # An unrecognised classification label cannot be ranked: fail closed.
                raise _Denied from None
            if not self._tenant_scoped(tenant, retrieved):
                raise _Denied
            classifications.extend(hit.chunk.classification for hit in retrieved)

        def model_call(_path: str) -> None:
            policy = self._c.egress_policy
            if policy is None:
                pending.append(
                    (
                        AuditEventType.EGRESS_DECISION,
                        {
                            "egress_decision": "denied",
                            "egress_reason": "no egress policy configured",
                            "egress_provider": self._egress_provider,
                            "egress_operation": EgressOperation.GENERATE.value,
                        },
                    )
                )
                raise _Denied
            # Each distinct level is checked on its own: combined_classification() returns None
            # when any document is unclassified, which would hide a classified sibling.
            allowed, reason = True, "allowed"
            try:
                for level in set(classifications) or {None}:
                    decision = policy.check(
                        classification=level,
                        provider=self._egress_provider,
                        operation=EgressOperation.GENERATE,
                    )
                    if not decision.allowed:
                        allowed, reason = False, decision.reason
                        break
                    reason = decision.reason
            except Exception:
                allowed, reason = False, "egress policy could not decide"
            pending.append(
                (
                    AuditEventType.EGRESS_DECISION,
                    {
                        "egress_decision": "allowed" if allowed else "denied",
                        "egress_reason": reason,
                        "egress_provider": self._egress_provider,
                        "egress_operation": EgressOperation.GENERATE.value,
                    },
                )
            )
            if not allowed:
                raise _Denied

        hooks: dict[str, Callable[..., None]] = {}
        if ControlPoint.RETRIEVAL_RESULT.value in self._app.hook_surface:
            hooks[ControlPoint.RETRIEVAL_RESULT.value] = retrieval
        if ControlPoint.PRE_MODEL_EGRESS.value in self._app.hook_surface:
            hooks[ControlPoint.PRE_MODEL_EGRESS.value] = model_call
        return hooks

    def _tenant_scoped(self, tenant: str, retrieved: list[RetrievedChunk]) -> bool:
        policy = self._c.tenant_policy
        if policy is None:
            return True
        try:
            return len(policy.filter_chunks(tenant, retrieved)) == len(retrieved)
        except Exception:
            return False

    def _admit_result(
        self,
        tenant: str,
        retrieved: list[RetrievedChunk],
        pending: list[tuple[AuditEventType, dict[str, Any]]],
    ) -> None:
        pending.append((AuditEventType.GUARD_DECISION, {}))
        if not self._tenant_scoped(tenant, retrieved):
            raise PolicyViolationError("result withheld at admission")

    def _admit_answer(
        self,
        query_id: str,
        text: str,
        pending: list[tuple[AuditEventType, dict[str, Any]]],
    ) -> str:
        guard = self._c.guard
        if guard is not None:
            result = guard.check_answer(Answer(query_id=query_id, text=text))
            if not result.allowed:
                raise SecurityError(result.reason or "Answer blocked by security guard.")
            if result.modified_content:
                text = result.modified_content
        redactor = self._c.redactor
        return redactor.redact(text) if redactor else text

    # -- normalization ------------------------------------------------------

    @staticmethod
    def _as_retrieved(doc: Mapping[str, Any]) -> RetrievedChunk:
        return RetrievedChunk(
            chunk=Chunk(
                id=str(doc["id"]),
                doc_id=str(doc["id"]),
                content=str(doc["text"]),
                tenant_id=doc.get("tenant_id"),
                classification=(
                    DataClassification(doc["classification"])
                    if doc.get("classification") is not None
                    else None
                ),
                metadata={"source": str(doc["source"])},
            ),
            score=1.0,
            rank=1,
            retrieval_method=RetrievalMethod.HYBRID,
        )

    @staticmethod
    def _citations(retrieved: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                chunk_id=hit.chunk.id,
                source=hit.chunk.metadata["source"],
                passage=hit.chunk.content,
                score=hit.score,
            )
            for hit in retrieved
        ]

    # -- evidence -----------------------------------------------------------

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        """`min(earned, ceiling)` per entry (ADR-0018 §7). What is earned comes
        from wired roles and what this adapter recorded for `context.request_id`;
        the ceiling comes from the application's own hook surface."""
        ceiling = evidence_ceiling(self.application_profile)
        earned = {
            EvidenceKind.IDENTITY_TENANT: self._enforced_if(
                isinstance(self._c.tenant_policy, TenantPolicy)
            ),
            EvidenceKind.RETRIEVAL_PROVENANCE: self._provenance.get(
                context.request_id, EvidenceStatus.UNSUPPORTED
            ),
            EvidenceKind.EGRESS_DECISION: self._enforced_if(
                isinstance(self._c.egress_policy, EgressPolicy)
            ),
            EvidenceKind.POLICY_DECISION: self._enforced_if(
                isinstance(self._c.guard, SecurityGuard)
            ),
            EvidenceKind.AUDIT_COMPLETION: self._enforced_if(
                isinstance(self._c.audit_sink, AuditSink)
                and bool(self._audit_complete.get(context.request_id))
            ),
            # The application reports no usage or cost, and no review queue is wired.
            EvidenceKind.USAGE_COST: EvidenceStatus.UNSUPPORTED,
            EvidenceKind.FEEDBACK_REVIEW_ROUTING: EvidenceStatus.UNSUPPORTED,
            EvidenceKind.STREAMING_PREVALIDATION: EvidenceStatus.UNSUPPORTED,
        }
        evidence = tuple(
            EvidenceEntry(kind, min(earned[kind], ceiling[kind], key=evidence_status_rank))
            for kind in EvidenceKind
        )
        return ConformanceReport(
            adapter_name=self.name(), adapter_version=self.engine_version(), evidence=evidence
        )

    @staticmethod
    def _enforced_if(condition: bool) -> EvidenceStatus:
        return EvidenceStatus.ENFORCED if condition else EvidenceStatus.UNSUPPORTED


__all__ = ["ADAPTER_VERSION", "ApplicationHandle", "ExistingGraphApplicationAdapter"]
