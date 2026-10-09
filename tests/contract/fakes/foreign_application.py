"""A fake *existing application* and the adapter that wraps it (Lot 22, ADR-0018 §13).

`ForeignApp` plays the part of a client application the framework does not own:
it has its own retriever, model calls, tools and streaming, and exposes hooks
only where its author chose to. A hook is either *blocking* (an exception it
raises stops the application) or *observe-only* (the application swallows it,
like a logging callback). That distinction is what makes `OBSERVED` and
`ENFORCED` genuinely different here rather than two labels.

`ForeignApplicationAdapter` implements `DocumentEngine` and
`ApplicationProfileProvider`. Its profile is derived from the application's
real hook surface, never declared independently, so the behavioural probes in
`test_application_behaviour.py` measure the profile against what the
application can actually do. Test-only on purpose: no
`adapters/applications/` package exists, and creating one is a separately
authorized task (CLAUDE.md block 07).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

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
from modular_rag.contracts.audit import AuditEventType
from modular_rag.contracts.engine import (
    EngineCapability,
    EngineRequest,
    EngineResult,
    EngineStep,
    ExecutionContext,
)
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import EngineCapabilityError, PolicyViolationError
from modular_rag.core.models.answer import Citation
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
APP_CLAIMED_TENANT = "app-claimed-tenant"

_HOOKABLE = frozenset(
    {
        ControlPoint.RETRIEVAL_RESULT,
        ControlPoint.PRE_MODEL_EGRESS,
        ControlPoint.TOOL_INVOCATION,
        ControlPoint.STREAM_CHUNK,
    }
)


class Denied(Exception):
    """Raised by a hook to ask the application to stop."""


@dataclass(frozen=True)
class Doc:
    tenant: str
    doc_id: str
    text: str
    source: str


DEFAULT_CORPUS = (
    Doc(TENANT_A, "a1", "alpha onboarding policy", "kb://a"),
    Doc(TENANT_B, "b1", "tenant-b confidential pricing", "kb://b"),
)


@dataclass(frozen=True)
class AppOutput:
    text: str
    docs: list[Doc]
    metadata: dict[str, Any]


class ForeignApp:
    """The application under wrap. Holds its own state and never sees a
    framework type."""

    def __init__(
        self,
        *,
        corpus: tuple[Doc, ...] = DEFAULT_CORPUS,
        hook_surface: dict[ControlPoint, bool] | None = None,
        model_paths: dict[str, bool] | None = None,
        tools: tuple[str, ...] = (),
        tenant_aware: bool = True,
        streams: bool = False,
        undeclared_egress: bool = False,
    ) -> None:
        surface = dict(hook_surface or {})
        unknown = set(surface) - _HOOKABLE
        if unknown:
            raise ValueError(f"not an application-owned hook: {sorted(unknown)}")
        self.hook_surface = surface
        # name -> "this call is routed through the pre-model hook"
        self.model_paths = dict(model_paths if model_paths is not None else {"completion": True})
        self.tools = tools
        self.tenant_aware = tenant_aware
        self.streams = streams
        self.undeclared_egress = undeclared_egress
        self._corpus = corpus
        self.invocations = 0
        self.received_tenants: list[str] = []
        self.provider_calls: list[str] = []
        self.tool_calls: list[str] = []

    def path_is_hooked(self, name: str) -> bool:
        return self.model_paths[name] and ControlPoint.PRE_MODEL_EGRESS in self.hook_surface

    def invoke(
        self, text: str, tenant: str, hooks: dict[ControlPoint, Callable[..., None]]
    ) -> AppOutput:
        docs = self._begin(tenant, hooks)
        for tool in self.tools:
            self._fire(ControlPoint.TOOL_INVOCATION, hooks, tool)
            self.tool_calls.append(tool)
        if self.undeclared_egress:
            self.provider_calls.append("telemetry-sink")
        return AppOutput(
            text=" | ".join(doc.text for doc in docs),
            docs=docs,
            # Deliberately claims a tenant: the adapter must keep it inert (ADR-0018 §10).
            metadata={"tenant_id": APP_CLAIMED_TENANT, "model": "fake-model"},
        )

    def stream(
        self, text: str, tenant: str, hooks: dict[ControlPoint, Callable[..., None]]
    ) -> Iterator[str]:
        docs = self._begin(tenant, hooks)
        for doc in docs:
            self._fire(ControlPoint.STREAM_CHUNK, hooks, doc.text)
            yield doc.text

    def _begin(self, tenant: str, hooks: dict[ControlPoint, Callable[..., None]]) -> list[Doc]:
        self.invocations += 1
        self.received_tenants.append(tenant)
        docs = [d for d in self._corpus if not self.tenant_aware or d.tenant == tenant]
        self._fire(ControlPoint.RETRIEVAL_RESULT, hooks, docs)
        for name in self.model_paths:
            if self.path_is_hooked(name):
                self._fire(ControlPoint.PRE_MODEL_EGRESS, hooks, name)
            self.provider_calls.append(name)
        return docs

    def _fire(
        self, point: ControlPoint, hooks: dict[ControlPoint, Callable[..., None]], *args: Any
    ) -> None:
        if point not in self.hook_surface or point not in hooks:
            return
        try:
            hooks[point](*args)
        except Exception:
            if self.hook_surface[point]:
                raise
            # observe-only hook: the application carries on, like a log callback


def _allow(*_args: Any) -> bool:
    return True


def _same_tenant_only(tenant: str, docs: list[Doc]) -> bool:
    return all(doc.tenant == tenant for doc in docs)


@dataclass
class Controls:
    """Framework-owned decisions. Every question asked is recorded in `calls`
    so a probe can tell a control that was *consulted* from one that merely
    exists."""

    admit_request: Callable[[str, str], bool] = _allow
    admit_retrieval: Callable[[str, list[Doc]], bool] = _allow
    admit_egress: Callable[[str, str], bool] = _allow
    admit_tool: Callable[[str, str], bool] = _allow
    admit_chunk: Callable[[str, str], bool] = _allow
    admit_result: Callable[[str, list[Doc]], bool] = _same_tenant_only
    calls: list[tuple[str, str]] = field(default_factory=list)


class AuditLog:
    """Recording sink whose writes can be made to fail per event type."""

    def __init__(self, fail_on: frozenset[AuditEventType] = frozenset()) -> None:
        self.events: list[AuditEventType] = []
        self.fail_on = fail_on

    def record(self, event: AuditEventType) -> None:
        if event in self.fail_on:
            raise RuntimeError(f"audit write failed for {event.value}")
        self.events.append(event)


class ForeignApplicationAdapter:
    """DocumentEngine + ApplicationProfileProvider over a `ForeignApp`."""

    def __init__(
        self,
        app: ForeignApp,
        *,
        controls: Controls | None = None,
        audit: AuditLog | None = None,
        review_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.app = app
        self.controls = controls if controls is not None else Controls()
        self.audit = audit if audit is not None else AuditLog()
        self._review_sink = review_sink
        self._provenance: dict[str, EvidenceStatus] = {}

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        return frozenset({EngineCapability.STREAMING}) if self.app.streams else frozenset()

    def name(self) -> str:
        return "foreign-fixture"

    def engine_version(self) -> str:
        return "0.0.1"

    @property
    def application_profile(self) -> ApplicationProfile:
        surface = self.app.hook_surface

        def support(point: ControlPoint) -> ControlPointSupport:
            if point in (ControlPoint.REQUEST_ADMISSION, ControlPoint.RESULT_ADMISSION):
                return ControlPointSupport.ENFORCED
            if point not in surface:
                return ControlPointSupport.UNAVAILABLE
            return (
                ControlPointSupport.ENFORCED if surface[point] else ControlPointSupport.OBSERVED
            )

        bindings = tuple(ControlPointBinding(point, support(point)) for point in ControlPoint)
        paths = tuple(
            EgressPath(
                name,
                EgressPathKind.MODEL,
                ControlPoint.PRE_MODEL_EGRESS if self.app.path_is_hooked(name) else None,
                support(ControlPoint.PRE_MODEL_EGRESS)
                if self.app.path_is_hooked(name)
                else ControlPointSupport.UNAVAILABLE,
            )
            for name in self.app.model_paths
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "adapter": self.engine_version(),
                    "surface": sorted((p.value, b) for p, b in surface.items()),
                    "paths": sorted(self.app.model_paths.items()),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return ApplicationProfile(
            application_name="foreign-fixture-app",
            application_version="0.0.1",
            adapter_version=self.engine_version(),
            integration_fingerprint=f"sha256:{fingerprint}",
            bindings=bindings,
            egress_paths=paths,
            expected_audit_events=tuple(
                ExpectedAuditEvent(event, mandatory=True)
                for event in sorted(required_audit_events(bindings, paths))
            ),
        )

    def _ask(self, kind: str, subject: str, decide: Callable[[], bool]) -> bool:
        """A control that cannot answer denies (ADR-0018 §12)."""
        self.controls.calls.append((kind, subject))
        try:
            return bool(decide())
        except Exception:
            return False

    def _hooks(
        self, tenant: str, pending: list[AuditEventType]
    ) -> dict[ControlPoint, Callable[..., None]]:
        controls = self.controls

        def gate(allowed: bool, event: AuditEventType | None) -> None:
            if event is not None:
                pending.append(event)
            if not allowed:
                raise Denied

        return {
            ControlPoint.RETRIEVAL_RESULT: lambda docs: gate(
                self._ask("retrieval", tenant, lambda: controls.admit_retrieval(tenant, docs)),
                AuditEventType.RETRIEVAL_PERFORMED,
            ),
            ControlPoint.PRE_MODEL_EGRESS: lambda path: gate(
                self._ask("egress", path, lambda: controls.admit_egress(tenant, path)),
                AuditEventType.EGRESS_DECISION,
            ),
            ControlPoint.TOOL_INVOCATION: lambda tool: gate(
                self._ask("tool", tool, lambda: controls.admit_tool(tenant, tool)), None
            ),
            ControlPoint.STREAM_CHUNK: lambda text: gate(
                self._ask("chunk", text, lambda: controls.admit_chunk(tenant, text)), None
            ),
        }

    def _admit(self, request: EngineRequest, context: ExecutionContext, pending: list) -> str:
        if not context.tenant_id:
            raise PolicyViolationError("no verified tenant context")
        tenant = context.tenant_id
        allowed = self._ask(
            "request", tenant, lambda: self.controls.admit_request(tenant, request.query.text)
        )
        pending.append(AuditEventType.GUARD_DECISION)
        if not allowed:
            raise PolicyViolationError("request denied at admission")
        return tenant

    def _flush(self, pending: list[AuditEventType]) -> None:
        for event in pending:
            self.audit.record(event)

    def _guarded(
        self, context: ExecutionContext, pending: list[AuditEventType], body: Callable[[], Any]
    ) -> Any:
        """Owns audit completion: a result is released only after every event
        was persisted, and a failed run is audited best-effort."""
        pending.insert(0, AuditEventType.QUERY_RECEIVED)
        self._provenance.pop(context.request_id, None)
        try:
            outcome = body()
            pending.append(AuditEventType.RUN_SUCCEEDED)
            self._flush(pending)
            return outcome
        except Exception:
            self._provenance.pop(context.request_id, None)
            failed = [e for e in pending if e is not AuditEventType.RUN_SUCCEEDED]
            failed.append(AuditEventType.RUN_FAILED)
            for event in failed:
                try:
                    self.audit.record(event)
                except Exception:
                    continue
            raise

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        pending: list[AuditEventType] = []

        def body() -> EngineResult:
            tenant = self._admit(request, context, pending)
            query = request.query.model_copy(update={"tenant_id": tenant})
            try:
                out = self.app.invoke(query.text, tenant, self._hooks(tenant, pending))
            except Denied as exc:
                raise PolicyViolationError("denied by a framework control") from exc
            allowed = self._ask("result", tenant, lambda: self.controls.admit_result(tenant, out.docs))
            pending.append(AuditEventType.GUARD_DECISION)
            if not allowed:
                raise PolicyViolationError("result withheld at admission")
            if self.app.model_paths:
                pending.append(AuditEventType.GENERATION_PERFORMED)
            if self._review_sink is not None:
                self._review_sink(context.request_id)
            retrieved = [self._as_retrieved(doc) for doc in out.docs]
            citations = [
                Citation(
                    chunk_id=hit.chunk.id,
                    source=hit.chunk.metadata["source"],
                    passage=hit.chunk.content,
                    score=hit.score,
                )
                for hit in retrieved
            ]
            self._provenance[context.request_id] = classify_provenance(citations, retrieved)
            return EngineResult(
                text=out.text,
                citations=citations,
                # Application-returned identity stays inert under its own key.
                metadata={"application": dict(out.metadata)},
            )

        return self._guarded(context, pending, body)  # type: ignore[no-any-return]

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult:
        return self.run(request, context)

    async def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        if EngineCapability.STREAMING not in self.capabilities:
            raise EngineCapabilityError(f"{self.name()} does not declare streaming")
        pending: list[AuditEventType] = []
        emitted: list[EngineStep] = []

        def body() -> None:
            tenant = self._admit(request, context, pending)
            try:
                for text in self.app.stream(request.query.text, tenant, self._hooks(tenant, pending)):
                    emitted.append(EngineStep("chunk", metadata={"text": text}))
            except Denied as exc:
                raise PolicyViolationError("stream fragment denied") from exc

        # Fragments are only handed to the caller once the run's audit is
        # complete; the denied chunk and everything after it never appears.
        self._guarded(context, pending, body)
        for step in emitted:
            yield step

    @staticmethod
    def _as_retrieved(doc: Doc) -> RetrievedChunk:
        return RetrievedChunk(
            chunk=Chunk(
                id=doc.doc_id,
                doc_id=doc.doc_id,
                content=doc.text,
                page=None,
                metadata={"source": doc.source},
            ),
            score=1.0,
            rank=1,
            retrieval_method=RetrievalMethod.HYBRID,
        )

    def conformance_report(self, context: ExecutionContext) -> ConformanceReport:
        """`min(earned, ceiling)` per entry, applied before the evidence tuple
        exists (ADR-0018 §7); `achieved_level` is still computed by the
        shared pure function."""
        profile = self.application_profile
        ceiling = evidence_ceiling(profile)
        earned = {
            EvidenceKind.IDENTITY_TENANT: EvidenceStatus.ENFORCED,
            EvidenceKind.RETRIEVAL_PROVENANCE: self._provenance.get(
                context.request_id, EvidenceStatus.UNSUPPORTED
            ),
            EvidenceKind.EGRESS_DECISION: EvidenceStatus.ENFORCED,
            EvidenceKind.POLICY_DECISION: EvidenceStatus.ENFORCED,
            EvidenceKind.AUDIT_COMPLETION: EvidenceStatus.ENFORCED,
            EvidenceKind.USAGE_COST: EvidenceStatus.OBSERVED,
            EvidenceKind.FEEDBACK_REVIEW_ROUTING: (
                EvidenceStatus.ENFORCED
                if self._review_sink is not None
                else EvidenceStatus.UNSUPPORTED
            ),
            EvidenceKind.STREAMING_PREVALIDATION: (
                EvidenceStatus.ENFORCED
                if EngineCapability.STREAMING in self.capabilities
                else EvidenceStatus.UNSUPPORTED
            ),
        }
        evidence = tuple(
            EvidenceEntry(
                kind, min(earned[kind], ceiling[kind], key=evidence_status_rank)
            )
            for kind in EvidenceKind
        )
        return ConformanceReport(
            adapter_name=self.name(), adapter_version=self.engine_version(), evidence=evidence
        )
