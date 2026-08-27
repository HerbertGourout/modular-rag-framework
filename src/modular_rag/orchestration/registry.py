from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from modular_rag.contracts.indexing import VectorIndexer
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import RegistryError
from modular_rag.orchestration.container import Container

log = structlog.get_logger(__name__)

_Factory = Callable[[ComponentConfig], Any]


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
            "review_queue": {},
            "audit_sink": {},
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
                ("review_queue", governance.review_queue),
                ("audit_sink", governance.audit_sink),
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

        log.info("registry.wired", pipeline_id=manifest.id)
        return container

