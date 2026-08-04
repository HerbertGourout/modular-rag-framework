from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from modular_rag.app.container import Container
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import RegistryError

log = structlog.get_logger(__name__)

_Factory = Callable[[ComponentConfig], Any]


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
            "evaluator": {},
            "planner": {},
            "graph_store": {},
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
        if manifest.evaluation:
            container.register("evaluator", self._build("evaluator", manifest.evaluation))

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

    @classmethod
    def default(cls) -> ComponentRegistry:
        """Return a registry pre-loaded with all built-in adapters."""
        from modular_rag.orchestration._default_factories import register_defaults

        reg = cls()
        register_defaults(reg)
        return reg
