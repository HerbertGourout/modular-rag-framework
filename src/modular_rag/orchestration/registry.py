from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

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

        log.info("registry.wired", pipeline_id=manifest.id)
        return container

