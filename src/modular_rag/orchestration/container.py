from __future__ import annotations

from typing import Any

import structlog

from modular_rag.contracts.audit import AuditSink
from modular_rag.contracts.chunking import Chunker
from modular_rag.contracts.egress import EgressPolicy
from modular_rag.contracts.embeddings import Embedder
from modular_rag.contracts.feedback import FeedbackSink
from modular_rag.contracts.generation import Generator
from modular_rag.contracts.indexing import Indexer
from modular_rag.contracts.lifecycle import LifecycleLedger
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.contracts.meter import Meter
from modular_rag.contracts.reranking import Reranker
from modular_rag.contracts.retrieval import Retriever
from modular_rag.contracts.review import ReviewQueue
from modular_rag.contracts.security import Redactor, SecurityGuard, TenantPolicy
from modular_rag.contracts.telemetry import Telemetry
from modular_rag.contracts.tracing import Tracer
from modular_rag.core.enums import ReadinessState
from modular_rag.core.errors import RegistryError
from modular_rag.core.models.health import DependencyHealth, ReadinessReport
from modular_rag.core.resilience import unhealthy_dependency

log = structlog.get_logger(__name__)

# Lot 6 (readiness and resilience): which registered roles are *critical* —
# their `check_health()` reporting unhealthy makes the whole pipeline
# UNREADY (HTTP 503), not merely DEGRADED. Role-derived, not class-derived
# (observability-expert review): criticality must match what actually
# happens on the request path, not an a-priori guess about which store
# "feels" more important.
#
# Single standard (orchestration-specialist review, Lot 6 — the original cut
# mixed a query-path standard for "retriever"/"lifecycle_ledger" with an
# ingest-path standard for "indexer", which is incoherent: it made a down
# Qdrant UNREADY even though `HybridRetriever` already degrades gracefully
# around it on the query path, the same fallback that earns "retriever" its
# non-critical rating): a role is critical only if its failure produces an
# **unhandled exception on the query-serving path** (`answer()`/`retrieve()`
# — what `/ready` actually gates traffic routing for), given `RAGEngine`'s
# real, current exception handling.
#
# - "audit_sink": *when wired*, `RAGEngine._audit()` calls
#   `self._c.audit_sink.record(event)` with no try/except, on both the
#   success and failure paths of `_run()` — a down audit sink already fails
#   every `/answer` call today. Reporting DEGRADED for it would misreport
#   "still serving traffic" when it isn't.
# - "generator": added Codex review HIGH-001 (second pass) — every valid
#   manifest wires one (`PipelineManifest.generator` is required), and
#   `RAGEngine._run_steps()` calls `self._c.generator.generate(query,
#   context, trace)` with no try/except; `_run()`'s own wrapping
#   try/except only records telemetry/audit before re-raising unchanged.
#   There is no generator fallback anywhere in this codebase — a broken
#   generator fails every `/answer` call exactly like a down audit sink.
#   `OpenAIGenerator`/`AnthropicGenerator` now both implement
#   `check_health()` (see those files) — a real, authenticated,
#   non-generative, cached probe against the specific configured model,
#   never a generation call.
# - "egress_policy": added 2026-09-14 with `OpaEgressPolicy`
#   (`adapters/policy/opa_egress_policy.py`). Every egress checkpoint
#   (`RAGEngine`'s embed/rerank/generate, `LangGraphEngineAdapter`'s handoff)
#   raises `EgressDeniedError` on a denial, and a policy that cannot reach its
#   decision service denies every remote call by design (fail-closed), so an
#   unreachable OPA fails `/answer` for a remote-provider pipeline exactly like
#   a down audit sink. Only a policy implementing `check_health()` is ever
#   probed: `ManifestEgressPolicy` has nothing external to check and is
#   unaffected, and `OpaEgressPolicy` reports no dependency at all when every
#   declared provider is local.
#
# Deliberately *not* critical under this standard:
# - "indexer" (Qdrant): not read directly by `answer()`/`retrieve()` at all —
#   only reached indirectly, through whichever retriever is wired. When that
#   retriever is `HybridRetriever` (both shipped presets), a down vector leg
#   is caught and gracefully degraded by `_safe_retrieve()`, same as a down
#   lexical leg. Only `ingest_chunks()` calls it unconditionally — an
#   ingest-path failure surfaces synchronously to whoever is running the
#   ingest job (CLI, batch process), not to a serving pod's traffic
#   eligibility, so it is out of `/ready`'s scope by design, not by omission.
# - "retriever": `HybridRetriever` already falls back to whichever leg is
#   still reachable (`_safe_retrieve()`).
# - "lifecycle_ledger": never read on the query path, only ingestion — same
#   ingest-path reasoning as "indexer" above.
#
# Residual risk, not silently elided: a manifest wiring a *bare*
# `VectorRetriever` or `PersistentSparseRetriever` as `retriever` (no
# `HybridRetriever` fallback) has no graceful degradation, so DEGRADED would
# be optimistic for that specific, currently-unused-by-any-shipped-preset
# configuration — `Container` has no visibility into a retriever's internal
# composition beyond the registered component itself, so this cannot be
# detected generically here.
_CRITICAL_ROLES = frozenset({"audit_sink", "egress_policy", "generator"})

# Codex review HIGH-002 (Lot 6): "would this raise an unhandled exception"
# is necessary but not sufficient for readiness — a pod with zero usable
# retrieval capacity cannot serve a useful RAG answer even though nothing
# raises: `HybridRetriever._safe_retrieve()` catches the failure and simply
# returns empty context. `secure-enterprise-rag.yaml` wires both the dense
# ("indexer") and sparse ("retriever") legs against the *same* Qdrant server
# (`indexer.config.url` and `retriever.config.url` are both `${QDRANT_URL}`)
# — if that one server goes down, both legs report unhealthy simultaneously,
# and under the plain per-role standard above this stayed DEGRADED/200 with
# no retrieval capacity left at all. `check_readiness()` escalates this
# specific combination — "indexer" unhealthy *and* "retriever" unhealthy —
# to UNREADY below, regardless of `_CRITICAL_ROLES` membership. This does
# NOT fire for the default `local-hybrid-rag` preset: its lexical leg is
# in-memory BM25, which has no `check_health()` at all, so "retriever"
# reports zero entries (not "unhealthy") and BM25 keeps serving lexical-only
# results on its own regardless of Qdrant's state — correctly DEGRADED, not
# UNREADY, since real capacity remains.
#
# Codex review HIGH-001 (second pass) also flagged the generator gap
# addressed above: neither generator implemented `check_health()` at all,
# so a down/unreachable LLM provider was invisible to `/ready` entirely.
# Both now do — see `generation/synthesizers/openai_gen.py` and
# `anthropic_gen.py` — and, since Codex review HIGH-003/HIGH-004 (third and
# fourth pass), the check is a real, authenticated, non-generative call
# (`client.models.retrieve(self.model)`, not `models.list()`, so it
# validates the *specific configured model*, not just that some model is
# listed) — a credential-presence-only check was verified live to report
# healthy for a deliberately invalid key. `/ready` never triggers an
# expensive LLM generation call (still honoring the Lot 6 acceptance
# criterion), but this does make a real, rate-limited-and-cached (30s TTL)
# network call, bounded to a short probe-specific timeout with no SDK
# retries (`with_options(timeout=..., max_retries=0)` — HIGH-002). Neither
# generator's probe detects a key that is valid for listing/retrieving
# model metadata but specifically out of quota for the chat/completion
# endpoint — that would require an actual generation call, still out of
# scope. Documented in each generator's own `check_health()` docstring and
# ADR-0010, not silently left unmentioned.


class Container:
    """Dependency-injection container for one wired pipeline."""

    def __init__(self, manifest: PipelineManifest) -> None:
        self.manifest = manifest
        self._store: dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        self._store[name] = component

    def close(self) -> None:
        """Best-effort graceful shutdown of registered resources."""
        for name, component in self._store.items():
            close = getattr(component, "close", None)
            if close is None:
                continue
            try:
                close()
            except Exception as exc:
                log.warning("container.close_failed", component=name, error=str(exc))

    def check_readiness(self) -> ReadinessReport:
        """Probe every registered component that implements
        `contracts.health.HealthCheckable` (duck-typed via `hasattr`, same
        discovery style as `close()` above — `orchestration/` may only
        import `core/` + `contracts/` + `orchestration/`, never a concrete
        adapter, so it can't `isinstance()`-check against one). Components
        with no `check_health()` (in-memory stores, `BM25Retriever`, a
        no-op audit sink) are silently skipped — nothing external to probe.

        Each returned `DependencyHealth` is stamped with the role it was
        probed under (test-specialist/orchestration-specialist review, Lot
        6): two components can share one `name()` — both Postgres adapters
        report `"postgres"` — and without `role`, a manifest wiring both
        `audit_sink` and `lifecycle_ledger` produces two indistinguishable
        entries in the same `/ready` payload, one critical and one not.

        A component's own `check_health()` raising is caught here, mirroring
        `close()`'s per-component `try/except` above (test-specialist
        review): every adapter shipped in this repo already catches
        internally, but discovery is duck-typed, so nothing stops a
        third-party or future component's `check_health()` from raising and
        turning `/ready` into an opaque 500 instead of an honest `503
        unready` naming the offending dependency.

        Beyond the plain per-role `_CRITICAL_ROLES` check, this also
        escalates to UNREADY when *both* "indexer" and "retriever" report
        every entry unhealthy — no retrieval leg is confirmed usable, even
        though nothing here technically raised (Codex review HIGH-002; see
        `_CRITICAL_ROLES`'s module comment above for the full rationale and
        the specific preset topology this addresses).
        """
        dependencies: list[DependencyHealth] = []
        critical_unhealthy = False
        any_unhealthy = False
        role_unhealthy: dict[str, bool] = {}
        for name, component in self._store.items():
            check_health = getattr(component, "check_health", None)
            if check_health is None:
                continue
            try:
                results = check_health()
            except Exception as exc:
                # Codex review MED-002 (Lot 6): /ready is unauthenticated —
                # never put a raw exception message in the public response.
                results = [unhealthy_dependency(name, exc)]
            results = [r.model_copy(update={"role": name}) for r in results]
            dependencies.extend(results)
            role_unhealthy[name] = bool(results) and all(not r.healthy for r in results)
            if any(not r.healthy for r in results):
                any_unhealthy = True
                if name in _CRITICAL_ROLES:
                    critical_unhealthy = True
        if role_unhealthy.get("indexer") and role_unhealthy.get("retriever"):
            critical_unhealthy = True
        if critical_unhealthy:
            status = ReadinessState.UNREADY
        elif any_unhealthy:
            status = ReadinessState.DEGRADED
        else:
            status = ReadinessState.HEALTHY
        return ReadinessReport(status=status, dependencies=dependencies)

    def _get(self, name: str) -> Any:
        if name not in self._store:
            raise RegistryError(f"Component '{name}' is not registered in the container.")
        return self._store[name]

    @property
    def chunker(self) -> Chunker:
        return self._get("chunker")

    @property
    def embedder(self) -> Embedder:
        return self._get("embedder")

    @property
    def indexer(self) -> Indexer:
        return self._get("indexer")

    @property
    def retriever(self) -> Retriever:
        return self._get("retriever")

    @property
    def reranker(self) -> Reranker | None:
        return self._store.get("reranker")

    @property
    def generator(self) -> Generator:
        return self._get("generator")

    @property
    def guard(self) -> SecurityGuard | None:
        return self._store.get("guard")

    @property
    def telemetry(self) -> Telemetry | None:
        return self._store.get("telemetry")

    @property
    def tracer(self) -> Tracer | None:
        """ADR-0012. Deliberately `.get()`-based (returns `None`, never
        raises for an unregistered role) — the same pattern as every other
        optional role below, not a "default to a no-op instance" pattern.
        See ADR-0012's own rationale for why a third container-property
        convention was deliberately avoided here."""
        return self._store.get("tracer")

    @property
    def meter(self) -> Meter | None:
        """ADR-0013 — same `.get()`-based optional-role pattern as `tracer`
        above."""
        return self._store.get("meter")

    @property
    def audit_sink(self) -> AuditSink | None:
        return self._store.get("audit_sink")

    @property
    def tenant_policy(self) -> TenantPolicy | None:
        return self._store.get("tenant_policy")

    @property
    def redactor(self) -> Redactor | None:
        return self._store.get("redactor")

    @property
    def egress_policy(self) -> EgressPolicy | None:
        """Lot 20 (docs/refactoring-plan.md) — same `.get()`-based optional-role
        pattern as `tenant_policy`/`redactor` above. `None` when no
        `governance.egress_policy` is configured; a pipeline behaves exactly
        as it did before this lot in that case."""
        return self._store.get("egress_policy")

    @property
    def review_queue(self) -> ReviewQueue | None:
        return self._store.get("review_queue")

    @property
    def feedback_sink(self) -> FeedbackSink | None:
        """ADR-0014 (Batch 14) — same `.get()`-based optional-role pattern as
        `audit_sink`/`review_queue` above. Not in `_CRITICAL_ROLES`:
        `RAGEngine.record_feedback()` is reached from a dedicated endpoint,
        never from `answer()`/`retrieve()`'s own hot path, so a down
        feedback sink cannot make the pipeline UNREADY for those."""
        return self._store.get("feedback_sink")

    @property
    def lifecycle_ledger(self) -> LifecycleLedger | None:
        return self._store.get("lifecycle_ledger")

    @property
    def policy_engine(self) -> Any | None:
        return self._store.get("policy_engine")
