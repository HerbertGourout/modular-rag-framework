"""DocumentEngine — the engine-neutral delegation boundary (ADR-0005 §5.2,
ADR-0006, docs/refactoring-plan.md Lot 7).

Every type here is vendor-neutral by design: no LangGraph (or any other
engine) type may appear in a public signature in this module. Adapters
(Lot 8: native/`RAGEngine`; Lot 15: LangGraph) translate to and from these
shapes at the adapter boundary — that translation is the only place vendor
types are allowed to exist.

Compatibility policy: see docs/architecture/document-engine-contract.md.
Schema version fields (`schema_version` on request/result) exist so that
policy can evolve independently of the Python Protocol's own version.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from modular_rag.core.models.answer import Citation
from modular_rag.core.models.query import Query

CONTRACT_VERSION = "1.0"


class EngineCapability(StrEnum):
    """What an adapter declares it supports. Callers MUST check
    `DocumentEngine.capabilities` before relying on a capability-gated method
    — calling `astream()` without `STREAMING` declared, for example, is a
    caller error (`EngineCapabilityError`), not something the engine should
    silently degrade."""

    STREAMING = "streaming"
    CANCELLATION = "cancellation"
    TOOL_USE = "tool_use"
    MULTI_TURN = "multi_turn"
    GOVERNANCE_INTERCEPT = "governance_intercept"


class CancellationToken:
    """Cooperative cancellation signal, engine-neutral. Wraps whatever the
    underlying engine's own cancellation primitive is (an asyncio Task, a
    LangGraph run id, ...) behind one small interface every adapter must
    honor if it declares `EngineCapability.CANCELLATION`.

    Deliberately not a dataclass/frozen type: cancellation is inherently
    mutable, shared, cross-task state.
    """

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True)
class GovernanceDecision:
    """Returned by a `GovernanceHook` — a `check()` result, deliberately
    shaped like `contracts.security.GuardResult` without importing it, so
    `engine.py` never depends on another contract module."""

    allowed: bool
    reason: str | None = None


@runtime_checkable
class GovernanceHook(Protocol):
    """Called by an adapter that declares `EngineCapability.GOVERNANCE_INTERCEPT`
    before executing a governed step (e.g. before generation), so the owned
    security/policy layer (ADR-0005 §5.1) can intercept engine-orchestrated
    steps without the engine needing to know about `SecurityGuard` directly.
    A concrete adapter over a real `SecurityGuard` lives in Lot 11c, not here.
    """

    def check(self, step_name: str, payload: dict[str, Any]) -> GovernanceDecision: ...


@dataclass(frozen=True)
class ExecutionContext:
    """Identity/tenant/correlation/cancellation carried through every
    DocumentEngine call. Engine-neutral — never contains vendor-specific
    state. `tenant_id` is the hook Lot 11b's fail-closed enforcement attaches
    to; it is not itself an enforcement mechanism here.

    `tenant_id` is `str | None` (Lot 1, tenant fail-closed): `None` means
    "no verified identity" and must be propagated as-is, never fabricated
    into a placeholder string. `TenantIsolationPolicy.enforce_query()`
    denies on any falsy `tenant_id` — a fabricated non-empty value (e.g.
    `"default"`) would silently defeat that fail-closed check. This field is
    the single authoritative identity source: an adapter must overwrite
    whatever tenant_id a `Query` already carries with this one, never merge
    or prefer the `Query`'s (see `NativeEngineAdapter`/`LangGraphEngineAdapter`).

    `roles` mirrors `contracts.identity.TenantContext.roles` — propagated
    for future RBAC/audit-actor consumers. No owned control-plane logic
    reads it yet; per docs/architecture/document-engine-contract.md's
    extension-envelope discipline ("never branch core control-plane logic
    on `extensions`' contents"), it is a typed field here, not stuffed into
    `extensions`.
    """

    tenant_id: str | None
    correlation_id: str
    request_id: str
    user_id: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    cancellation_token: CancellationToken | None = None
    governance_hook: GovernanceHook | None = None
    extensions: dict[str, Any] = field(default_factory=dict)  # extension envelope, see policy doc


@dataclass(frozen=True)
class EngineRequest:
    """Normalized request — a `DocumentEngine.run()` input."""

    query: Query
    context_chunks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class EngineStep:
    """One orchestration step. Shape-compatible with
    `core.models.trace.TraceStep` on purpose, so an engine's execution maps
    onto our own audit trail (Lot 10) without the engine needing to know our
    `TraceStep` type."""

    name: str
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineResult:
    """Normalized result — a `DocumentEngine.run()` output."""

    text: str
    citations: list[Citation] = field(default_factory=list)
    steps: list[EngineStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CONTRACT_VERSION


@runtime_checkable
class DocumentEngine(Protocol):
    """The delegation boundary itself. Adapters implement this against a
    specific external engine (LangGraph first, per ADR-0006) or against the
    native `RAGEngine` (Lot 8) — callers on either side of this Protocol
    never see vendor types.
    """

    @property
    def capabilities(self) -> frozenset[EngineCapability]:
        """Declared, not probed — callers check this before calling a
        capability-gated method."""
        ...

    def run(self, request: EngineRequest, context: ExecutionContext) -> EngineResult: ...

    async def arun(self, request: EngineRequest, context: ExecutionContext) -> EngineResult: ...

    def astream(
        self, request: EngineRequest, context: ExecutionContext
    ) -> AsyncIterator[EngineStep]:
        """Only valid if `EngineCapability.STREAMING` is declared — otherwise
        raise `EngineCapabilityError` (see semantic conformance suite,
        tests/contract/test_engine_conformance.py)."""
        ...

    def name(self) -> str: ...

    def engine_version(self) -> str: ...
