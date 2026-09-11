from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from modular_rag.contracts.assurance import (
    AssuranceLevel,
    EvidenceEntry,
    EvidenceKind,
    EvidenceStatus,
    assurance_level_rank,
    compute_achieved_level,
)
from modular_rag.contracts.audit import AuditSink
from modular_rag.contracts.egress import EgressPolicy
from modular_rag.contracts.indexing import VectorIndexer
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.contracts.meter import Meter
from modular_rag.contracts.review import ReviewQueue
from modular_rag.contracts.security import SecurityGuard, TenantPolicy
from modular_rag.core.errors import RegistryError
from modular_rag.orchestration.container import Container

log = structlog.get_logger(__name__)

_Factory = Callable[[ComponentConfig], Any]

# Lot 20 corrective pass (Codex review pass 1, HIGH-001): the built-in remote provider types
# this framework itself registers (app/default_factories.py) -- deliberately scoped to exactly
# these three, not "any type this manifest declares that isn't explicitly local." A blanket
# "unrecognized type -> deny" rule would also catch every test-double type name
# (test_registry.py's "fake-generator"/"fake-embedder" etc.) that has never had anything to do
# with egress, breaking dozens of unrelated tests for no security benefit. Scoping to the actual
# shipped remote adapters closes the real gap (a manifest wiring "openai"/"anthropic" with no
# governance.egress_policy silently sent content to that provider) without that collateral
# damage. Lives here, not in contracts/egress.py, so contracts/ stays fully vendor-neutral per
# CLAUDE.md §07 ("no OpenAI/Anthropic semantics into core contracts") -- orchestration/registry.py
# already references concrete built-in names locally for the same reason (the "native"/"langgraph"
# engine.adapter check below).
_KNOWN_REMOTE_PROVIDER_TYPES = frozenset({"openai", "anthropic", "openai-embeddings"})


def _capability_evidence(
    *,
    adapter: str,
    tenant_policy_usable: bool,
    guard_usable: bool,
    policy_engine_usable: bool,
    egress_policy_usable: bool,
    audit_sink_usable: bool,
    review_queue_usable: bool,
    meter_usable: bool,
) -> tuple[EvidenceEntry, ...]:
    """The *capability* profile of one wiring: the best status each
    `EvidenceKind` could reach for a request this pipeline actually serves.

    Deliberately distinct from `DocumentEngine.conformance_report()`, which
    reports what was true for one specific request (Codex review pass 1,
    HIGH-002: "separate a configuration capability profile from per-execution
    evidence"). The difference matters for exactly two kinds:

    - `RETRIEVAL_PROVENANCE` is `VERIFIED` here because both shipped engines
      run the framework-owned grounding check
      (`contracts.assurance.classify_provenance()`) on every request, so this
      wiring *can* produce verified provenance. A real report only claims it
      once a request has actually earned it.
    - `USAGE_COST` is `OBSERVED` here when a `Meter` is wired on the native
      engine, because a generator *may* emit token/cost evidence; a real
      report only claims it when one actually did.

    Never used to build a `ConformanceReport` — a capability is not evidence,
    and conflating the two is what produced the defect this function exists
    to close. It answers one question only: "may this wiring be allowed to
    declare `assurance.min_level: X` before serving traffic?"
    """
    is_langgraph = adapter == "langgraph"
    # LangGraph never reaches RAGEngine's audit emission, human-review
    # queueing, or generation token/cost metrics; governance.audit_sink,
    # review_queue and feedback_sink are themselves rejected for this adapter
    # below, so these are structurally unreachable rather than merely unwired.
    return (
        EvidenceEntry(
            EvidenceKind.IDENTITY_TENANT,
            EvidenceStatus.ENFORCED if tenant_policy_usable else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(EvidenceKind.RETRIEVAL_PROVENANCE, EvidenceStatus.VERIFIED),
        EvidenceEntry(
            EvidenceKind.EGRESS_DECISION,
            EvidenceStatus.ENFORCED if egress_policy_usable else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(
            EvidenceKind.POLICY_DECISION,
            EvidenceStatus.ENFORCED
            if (guard_usable or (policy_engine_usable and not is_langgraph))
            else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(
            EvidenceKind.AUDIT_COMPLETION,
            EvidenceStatus.ENFORCED
            if (audit_sink_usable and not is_langgraph)
            else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(
            EvidenceKind.USAGE_COST,
            EvidenceStatus.OBSERVED
            if (meter_usable and not is_langgraph)
            else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(
            EvidenceKind.FEEDBACK_REVIEW_ROUTING,
            EvidenceStatus.ENFORCED
            if (review_queue_usable and not is_langgraph)
            else EvidenceStatus.UNSUPPORTED,
        ),
        EvidenceEntry(
            EvidenceKind.STREAMING_PREVALIDATION,
            EvidenceStatus.ENFORCED
            if (is_langgraph and (guard_usable or egress_policy_usable))
            else EvidenceStatus.UNSUPPORTED,
        ),
    )


def _declared_capability_evidence(
    manifest: PipelineManifest, adapter: str
) -> tuple[EvidenceEntry, ...]:
    """Pre-construction capability profile, from raw manifest fields only.

    Advisory and deliberately optimistic: nothing is constructed yet, so a
    declared role is taken at face value. `validate_capabilities()` is a
    dry-run by definition (`mrag validate` never builds a component), so this
    is the strongest check available there -- it is necessary, not sufficient.
    `ComponentRegistry.wire()` re-checks the same requirement against the
    *constructed* components (`_wired_capability_evidence()` below), which is
    the authoritative gate; a manifest that passes here can still be rejected
    there when a declared role turns out not to satisfy its Protocol
    (Codex review pass 1, HIGH-002).
    """
    governance = manifest.governance
    observability = manifest.observability
    return _capability_evidence(
        adapter=adapter,
        tenant_policy_usable=governance is not None and governance.tenant_policy is not None,
        guard_usable=manifest.security is not None,
        policy_engine_usable=governance is not None and governance.policy_engine is not None,
        egress_policy_usable=governance is not None and governance.egress_policy is not None,
        audit_sink_usable=governance is not None and governance.audit_sink is not None,
        review_queue_usable=governance is not None and governance.review_queue is not None,
        meter_usable=observability is not None and observability.meter is not None,
    )


def _wired_capability_evidence(container: Container, adapter: str) -> tuple[EvidenceEntry, ...]:
    """Post-construction capability profile, from the components `wire()`
    actually built -- the authoritative input to the `assurance.min_level`
    gate.

    A role counts only when it satisfies its contract Protocol. Codex review
    pass 1 (HIGH-002) reproduced the gap this closes: registering a plain
    `object()` as guard/tenant_policy/egress_policy/audit_sink passed an
    `assurance.min_level: l2` manifest, reported L2, and then failed the very
    first request with `AttributeError`. `isinstance()` against a
    `runtime_checkable` Protocol is a pure in-memory structural check -- the
    same mechanism this module already applies to `VectorIndexer` (ADR-0009),
    with no network call and nothing instantiated.

    **What this gate does not promise** (Codex review pass 2, HIGH-002;
    accepted as a documented risk by the maintainer on 2026-09-11, ADR-0017
    §9). `runtime_checkable` validates method *presence* only -- never a
    signature, and never enforcement behaviour. A registered control that
    implements the expected names and does nothing (an `enforce_query()` that
    returns `None` for a missing tenant) still satisfies
    `assurance.min_level: l2` here. This is a limit of the mechanism, not an
    oversight: no startup-time check can prove a component enforces anything
    without executing it, and a gate that ran real governance decisions during
    `wire()` would be a different, far more invasive contract.

    The gate therefore answers exactly one question -- *are the controls this
    level requires declared and structurally wired?* -- and every document
    describing it says so in those words. Proving a control actually enforces
    is the job of the behavioural conformance harness
    (`tests/contract/test_engine_conformance.py`), which refuses to certify a
    claim at `ENFORCED` unless a denied or failing control demonstrably stops
    the request. Operators running third-party controls at L2 must run that
    harness against them; the startup gate alone is not evidence of
    enforcement.
    """
    return _capability_evidence(
        adapter=adapter,
        tenant_policy_usable=isinstance(container.tenant_policy, TenantPolicy),
        guard_usable=isinstance(container.guard, SecurityGuard),
        # Container.policy_engine is typed `Any` -- no PolicyEngine Protocol
        # exists -- so validate the one method RAGEngine._run_steps() calls.
        policy_engine_usable=callable(getattr(container.policy_engine, "enforce_query", None)),
        egress_policy_usable=isinstance(container.egress_policy, EgressPolicy),
        audit_sink_usable=isinstance(container.audit_sink, AuditSink),
        review_queue_usable=isinstance(container.review_queue, ReviewQueue),
        meter_usable=isinstance(container.meter, Meter),
    )


def _assurance_level_error(
    achievable: AssuranceLevel, minimum: AssuranceLevel, adapter: str, *, constructed: bool
) -> str:
    stage = "the components it wired" if constructed else "this manifest"
    return (
        f"assurance.min_level={minimum.value!r} is not achievable by {stage} under "
        f"engine.adapter={adapter!r}: the strongest level this wiring can guarantee is "
        f"{achievable.value!r}. Configure the governance/observability roles this level "
        "requires, or lower assurance.min_level."
    )


def runtime_manifest_errors(manifest: PipelineManifest) -> list[str]:
    """Return declarations that the selected online runtime cannot consume.

    Evaluation scorers and regression gates require a golden answer/dataset and
    therefore belong to the offline evaluation runner, not the online answer
    pipeline. LangGraph currently implements only the security-critical guard,
    tenant-isolation and redaction subset of the owned control plane.
    """
    errors: list[str] = []
    if manifest.evaluation is not None:
        errors.append(
            "evaluation is an offline golden-set concern and cannot be declared in a "
            "runnable pipeline manifest"
        )
    if manifest.quality is not None and (
        manifest.quality.gate is not None or manifest.quality.eval_profile is not None
    ):
        errors.append(
            "quality is an offline evaluation concern and cannot be declared in a runnable "
            "pipeline manifest"
        )

    if manifest.governance:
        # Codex review finding (Lot 1, second pass): these two tenant
        # invariants used to live only in app/config_resolution.py::
        # validate_capabilities(), which every bootstrap loader
        # (load_pipeline/load_engine/load_application) calls before
        # wire() — but ComponentRegistry.wire() is itself a public
        # primitive, reachable directly (tests, docs, any future caller
        # of create_default_registry()), and only ran this function,
        # which didn't check either invariant. Moved here so both entry
        # points share one enforcement point — validate_capabilities()
        # already folds this function's errors into its own return value.
        # (No local `governance = manifest.governance` alias here on
        # purpose: the `langgraph` block below reassigns that same name
        # from an Optional-typed expression, which mypy then flags as
        # incompatible with the non-Optional type this block's assignment
        # would have narrowed it to — direct attribute access sidesteps it.)
        if manifest.governance.tenant_enforcement and manifest.governance.tenant_policy is None:
            errors.append(
                "governance.tenant_enforcement=true requires governance.tenant_policy to be "
                "set — declared intent with no activatable implementation is not a valid "
                "manifest (ADR-0007 §3)."
            )
        if (
            not manifest.governance.tenant_enforcement
            and manifest.governance.tenant_policy is not None
        ):
            # Container.tenant_policy gates enforcement on presence alone
            # (RAGEngine/LangGraphEngineAdapter both check
            # `if self._c.tenant_policy:`, never this flag) — a manifest
            # with tenant_enforcement=false and a tenant_policy configured
            # is not a harmless no-op, it wires and enforces isolation
            # regardless of what the flag claims.
            errors.append(
                "governance.tenant_policy is set but governance.tenant_enforcement=false — "
                "this manifest claims tenant isolation is off while wiring a component that "
                "enforces it unconditionally regardless of this flag. Set "
                "tenant_enforcement=true, or remove tenant_policy."
            )
    # Lot 20 (docs/refactoring-plan.md): "Reject an incompatible manifest before startup" --
    # deliberately unconditional (not nested inside `if manifest.governance:`), since the gap
    # this closes is exactly a manifest with *no* governance section at all wiring a known
    # remote generator/embedder. Reads the raw config dict directly (not security.policies.
    # egress_policy.ManifestEgressPolicy) -- orchestration/ may import only core/ + contracts/ +
    # orchestration/, never security/ (a domain module); this mirrors every other check in this
    # function, which inspects manifest.* fields only.
    egress_policy_cfg = manifest.governance.egress_policy if manifest.governance else None
    configured_providers = (
        set(egress_policy_cfg.config.get("providers", {})) if egress_policy_cfg else set()
    )
    wired_provider_types = {
        ("embedder", manifest.embedder.type),
        ("generator", manifest.generator.type),
    }
    if manifest.reranker is not None:
        wired_provider_types.add(("reranker", manifest.reranker.type))
    for role, provider_type in wired_provider_types:
        if provider_type in configured_providers:
            continue
        if egress_policy_cfg is not None:
            # An explicit governance.egress_policy was configured but doesn't cover this
            # wired type -- always an error, regardless of what the type is (operator-declared
            # policies must be complete, not partially applied).
            errors.append(
                f"governance.egress_policy is configured but has no "
                f"providers[{provider_type!r}] entry for the wired {role} — every "
                "component type reachable through an egress checkpoint must have an "
                "explicit profile (local: true, or local: false with "
                "max_classification set)."
            )
        elif provider_type in _KNOWN_REMOTE_PROVIDER_TYPES:
            # No governance.egress_policy configured at all, AND this wired type is one of
            # this framework's own known remote providers (Codex review pass 1, HIGH-001):
            # fail closed by default rather than silently sending content to it with zero
            # protection. Any other, unrecognized type (a test double, a future custom
            # adapter) is unaffected -- this is not "unknown types are denied," only "these
            # specific built-in remote types require an explicit decision."
            errors.append(
                f"{role} type {provider_type!r} is a known remote provider, but no "
                "governance.egress_policy is configured to cover it. A manifest wiring "
                f"{provider_type!r} must configure governance.egress_policy explicitly "
                "(even to declare it fully allowed) -- unconfigured remote providers are "
                "denied by default (Lot 20 fail-closed default, ADR-0016 §2)."
            )

    adapter = manifest.engine.adapter if manifest.engine else "native"
    if adapter not in {"native", "langgraph"}:
        errors.append(
            f"Unknown engine.adapter {adapter!r}. Expected 'native' or 'langgraph'."
        )
    if adapter == "langgraph":
        governance = manifest.governance
        unsupported = {
            "governance.policy_engine": governance.policy_engine if governance else None,
            "governance.review_queue": governance.review_queue if governance else None,
            "governance.audit_sink": governance.audit_sink if governance else None,
            # ADR-0014 (Batch 14): read only from RAGEngine.record_feedback(),
            # which — like review_queue/audit_sink — LangGraphEngineAdapter
            # never reaches (it never calls into RAGEngine at all). Same
            # ADR-0008 boundary, same treatment.
            "governance.feedback_sink": governance.feedback_sink if governance else None,
            "observability.telemetry": (
                manifest.observability.telemetry if manifest.observability else None
            ),
        }
        # ADR-0012 correction (Codex review, pass 1, HIGH-001): `observability.tracer`
        # (and, per ADR-0013, `observability.meter` for the identical reason) deliberately
        # does NOT go in the `unsupported` dict above. Unlike `telemetry`/`audit_sink`/
        # `policy_engine`/`review_queue` (read only from inside
        # `RAGEngine._run_steps()`/`_run()`, never reached at all under
        # `engine.adapter='langgraph'`), `Container.tracer`/`Container.meter` are also
        # read directly by `app/application.py::ApplicationService.answer()`/`retrieve()`
        # (the `"app.request"` span, plus — per ADR-0013 — the `mrag.request.duration_ms`/
        # `mrag.request.errors` metrics recorded at that same boundary) and `api/__init__.py`
        # (the `"api.answer"`/`"api.retrieve"` spans) — both engine-neutral boundaries that
        # run identically regardless of which `DocumentEngine` is selected. A LangGraph
        # manifest with `observability.tracer`/`observability.meter` configured does NOT
        # silently ignore either (ADR-0008's actual concern): those two layers' spans and
        # request-level metrics are created exactly as documented. Only `RAGEngine`-internal
        # spans (`rag.answer`, `rag.guard_query`, ...) and pipeline-stage metrics
        # (`mrag.guard.rejections`, `mrag.generation.tokens`, ...) are unavailable under
        # LangGraph, because `LangGraphEngineAdapter` never calls into `RAGEngine` at all —
        # that is a real, narrower, and already-documented scope boundary (ADR-0012's own
        # "LangGraphEngineAdapter internal step instrumentation" out-of-scope note, extended
        # by ADR-0013 to cover the equivalent pipeline-stage metrics), not a case of a
        # declared control being ignored.
        for path, value in unsupported.items():
            if value is not None:
                errors.append(
                    f"{path} is not consumed by engine.adapter='langgraph'; "
                    "remove it or select the native engine"
                )

    # Lot 21 (ADR-0017, Accepted 2026-09-10): "A manifest requiring an unavailable
    # assurance level or mandatory control is rejected before any request is served."
    # This is the *dry-run* half, reachable from validate_capabilities()/`mrag validate`
    # where nothing is constructed, so it can only take a declared role at face value
    # (see _declared_capability_evidence's docstring). ComponentRegistry.wire() re-runs
    # the same requirement against the components it actually built, which is the
    # authoritative gate -- Codex review pass 1, HIGH-002.
    min_level = manifest.assurance.min_level if manifest.assurance else None
    if min_level is not None:
        achievable = compute_achieved_level(_declared_capability_evidence(manifest, adapter))
        if assurance_level_rank(achievable) < assurance_level_rank(min_level):
            errors.append(
                _assurance_level_error(achievable, min_level, adapter, constructed=False)
            )
    return errors


class ComponentRegistry:
    """Map component type names → factory functions, then wire a manifest into a Container."""

    def __init__(self) -> None:
        self._factories: dict[str, dict[str, _Factory]] = {
            "chunker": {},
            "embedder": {},
            "indexer": {},
            "retriever": {},
            "reranker": {},
            "generator": {},
            "guard": {},
            "tenant_policy": {},
            "policy_engine": {},
            "redactor": {},
            "egress_policy": {},
            "review_queue": {},
            "audit_sink": {},
            "feedback_sink": {},
            "telemetry": {},
            "tracer": {},
            "meter": {},
            "lifecycle_ledger": {},
        }

    def register(self, role: str, type_name: str, factory: _Factory) -> None:
        if role not in self._factories:
            self._factories[role] = {}
        self._factories[role][type_name] = factory
        log.debug("registry.registered", role=role, type=type_name)

    def available_types(self, role: str) -> frozenset[str]:
        """Public introspection: which type names are registered for a role.
        Added in Lot 9 (docs/refactoring-plan.md) so capability-validation
        code doesn't need to reach into `_factories` directly."""
        return frozenset(self._factories.get(role, {}))

    def _build(self, role: str, cfg: ComponentConfig | None) -> Any | None:
        if cfg is None:
            return None
        factories = self._factories.get(role, {})
        factory = factories.get(cfg.type)
        if factory is None:
            raise RegistryError(
                f"No factory for role='{role}' type='{cfg.type}'. "
                f"Available: {list(factories.keys())}"
            )
        return factory(cfg)

    def wire(self, manifest: PipelineManifest) -> Container:
        activation_errors = runtime_manifest_errors(manifest)
        if activation_errors:
            raise RegistryError("Invalid runtime manifest: " + "; ".join(activation_errors))
        container = Container(manifest)
        container.register("chunker", self._build("chunker", manifest.chunker))
        container.register("embedder", self._build("embedder", manifest.embedder))
        container.register("indexer", self._build("indexer", manifest.indexer))
        container.register("retriever", self._build("retriever", manifest.retriever))
        if manifest.reranker:
            container.register("reranker", self._build("reranker", manifest.reranker))
        container.register("generator", self._build("generator", manifest.generator))
        if manifest.security:
            container.register("guard", self._build("guard", manifest.security))
        if manifest.governance:
            governance = manifest.governance
            for role, cfg in (
                ("tenant_policy", governance.tenant_policy),
                ("policy_engine", governance.policy_engine),
                ("redactor", governance.redactor),
                ("egress_policy", governance.egress_policy),
                ("review_queue", governance.review_queue),
                ("audit_sink", governance.audit_sink),
                ("feedback_sink", governance.feedback_sink),
            ):
                if cfg:
                    container.register(role, self._build(role, cfg))
        if manifest.observability and manifest.observability.telemetry:
            container.register(
                "telemetry", self._build("telemetry", manifest.observability.telemetry)
            )
        if manifest.observability and manifest.observability.tracer:
            container.register(
                "tracer", self._build("tracer", manifest.observability.tracer)
            )
        if manifest.observability and manifest.observability.meter:
            container.register(
                "meter", self._build("meter", manifest.observability.meter)
            )
        if manifest.lifecycle and manifest.lifecycle.ledger:
            container.register(
                "lifecycle_ledger",
                self._build("lifecycle_ledger", manifest.lifecycle.ledger),
            )
        # Post-wiring: inject embedder and store into vector/hybrid retriever.
        # VectorRetriever needs an Embedder to embed queries and a QdrantStore to
        # call retrieve_by_vector() — both are separate components in the manifest.
        retriever = container.retriever
        embedder = container.embedder
        store = container.indexer
        if retriever is not None:
            for target in [retriever, getattr(retriever, "_vector", None)]:
                if target is None:
                    continue
                if embedder is not None and hasattr(target, "_embedder"):
                    target._embedder = embedder
                if store is not None and hasattr(target, "_store"):
                    target._store = store

        # ADR-0009: a dimension-sensitive Indexer (Qdrant today; any future
        # vector store implementing VectorIndexer) needs the wired Embedder
        # to reconcile its configured vector size — derived when the
        # manifest left it unset, validated with ConfigurationError on an
        # explicit mismatch. `isinstance()` against a Protocol is a pure
        # in-memory structural check (no network call, and does not itself
        # touch `embedder.dimensions`). `bind_embedder()` is a real
        # `VectorIndexer` protocol method (not a private-attribute
        # convention orchestration merely hopes an implementation reads —
        # Codex review, second pass) — the store decides internally whether
        # to call `ensure_vector_size(embedder.dimensions)` immediately or
        # defer it to its own first real connection, so a custom embedder
        # whose `.dimensions` requires loading a real model is never forced
        # to do so merely because wire() ran (CLAUDE.md §05.7's lazy-import
        # invariant; see ADR-0009).
        if embedder is not None and isinstance(store, VectorIndexer):
            store.bind_embedder(embedder)

        # Lot 21 (Codex review pass 1, HIGH-002): the authoritative
        # assurance.min_level gate. runtime_manifest_errors() above already
        # rejected a manifest that *declares* too little, but that check runs
        # before anything is constructed and therefore cannot tell a real
        # TenantPolicy from a plain object(). This one inspects what was
        # actually built, so a role that does not satisfy its contract
        # Protocol can no longer satisfy a declared minimum level and then
        # fail the first request instead.
        min_level = manifest.assurance.min_level if manifest.assurance else None
        if min_level is not None:
            adapter = manifest.engine.adapter if manifest.engine else "native"
            achievable = compute_achieved_level(_wired_capability_evidence(container, adapter))
            if assurance_level_rank(achievable) < assurance_level_rank(min_level):
                raise RegistryError(
                    "Invalid runtime manifest: "
                    + _assurance_level_error(achievable, min_level, adapter, constructed=True)
                )

        log.info("registry.wired", pipeline_id=manifest.id)
        return container

