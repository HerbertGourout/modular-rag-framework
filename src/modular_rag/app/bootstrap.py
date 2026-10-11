from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from modular_rag.app.application import ApplicationService
from modular_rag.app.config_resolution import resolve_manifest, validate_capabilities
from modular_rag.app.default_factories import create_default_registry
from modular_rag.contracts.application import ApplicationProfileProvider, evidence_ceiling
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.core.errors import ConfigurationError, ManifestError
from modular_rag.orchestration.container import Container
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter
from modular_rag.orchestration.registry import (
    EXISTING_GRAPH_ADAPTER,
    ComponentRegistry,
    application_assurance_error,
)

if TYPE_CHECKING:
    from modular_rag.contracts.engine import DocumentEngine


def load_manifest(path: str | Path) -> PipelineManifest:
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"Manifest not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"Invalid YAML in {p}: {exc}") from exc
    return PipelineManifest.model_validate(raw)


def load_pipeline(path: str | Path) -> RAGEngine:
    """Load a manifest and return a ready-to-use RAGEngine.

    This is the stable compatibility facade (Lot 8, docs/refactoring-plan.md)
    — existing direct Python callers and examples keep working against the
    concrete `RAGEngine` unchanged. API and CLI use `load_application()`.
    Prefer `load_native_engine()` for new
    code that wants the engine-neutral `DocumentEngine` port instead.
    """
    manifest = resolve_manifest(path)
    adapter_name = manifest.engine.adapter if manifest.engine else "native"
    if adapter_name != "native":
        raise ConfigurationError(
            f"load_pipeline() only supports engine.adapter='native', got {adapter_name!r}. "
            "Use load_engine() or load_application() for delegated engines."
        )
    registry = create_default_registry()
    _raise_for_manifest_errors(manifest, registry)
    container = registry.wire(manifest)
    return RAGEngine(container)


def load_native_engine(path: str | Path) -> NativeEngineAdapter:
    """Load a manifest and return it wrapped in the `DocumentEngine`-conformant
    native adapter (Lot 8). Rollback is simply calling `load_pipeline()`
    instead and using the returned `RAGEngine` directly, as before — both
    wrap the identical `wire()` output, so switching between them changes
    nothing about which components run, only which port callers see.
    """
    return NativeEngineAdapter(load_pipeline(path))


def load_engine(path: str | Path) -> DocumentEngine:
    """Load a manifest and return the `DocumentEngine` adapter its `engine`
    section selects (Lot 15, docs/refactoring-plan.md). A manifest with no
    `engine` section, or `engine.adapter: "native"`, gets
    `NativeEngineAdapter` — identical to `load_native_engine()`.
    `engine.adapter: "langgraph"` gets `LangGraphEngineAdapter` instead,
    wrapping the same wired `Container` (both adapters run the identical
    chunker/retriever/guard/generator selection — only the orchestration
    engine differs). An unrecognized adapter name raises `ConfigurationError`
    rather than silently falling back to native.
    """
    manifest = resolve_manifest(path)
    registry = create_default_registry()
    _raise_for_manifest_errors(manifest, registry)
    container = registry.wire(manifest)
    adapter_name = manifest.engine.adapter if manifest.engine else "native"

    if adapter_name == "native":
        return NativeEngineAdapter(RAGEngine(container))
    if adapter_name == "langgraph":
        from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter

        return LangGraphEngineAdapter(container)
    if adapter_name == EXISTING_GRAPH_ADAPTER:
        return _load_existing_graph_adapter(manifest, container)
    raise ConfigurationError(
        f"Unknown engine.adapter {adapter_name!r} in manifest {path!r}. "
        f"Expected 'native', 'langgraph' or {EXISTING_GRAPH_ADAPTER!r}."
    )


def load_application(path: str | Path) -> ApplicationService:
    """Load one manifest into the stable application facade.

    Startup resolution, component wiring and engine selection happen once;
    API and CLI therefore honor `${VAR}`, `secret://` and `engine.adapter`.
    """
    manifest = resolve_manifest(path)
    registry = create_default_registry()
    _raise_for_manifest_errors(manifest, registry)
    container = registry.wire(manifest)
    native = RAGEngine(container)
    adapter_name = manifest.engine.adapter if manifest.engine else "native"
    if adapter_name == "native":
        selected: DocumentEngine = NativeEngineAdapter(native)
    elif adapter_name == "langgraph":
        from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter

        selected = LangGraphEngineAdapter(container)
    elif adapter_name == EXISTING_GRAPH_ADAPTER:
        selected = _load_existing_graph_adapter(manifest, container)
    else:
        raise ConfigurationError(
            f"Unknown engine.adapter {adapter_name!r} in manifest {path!r}. "
            f"Expected 'native', 'langgraph' or {EXISTING_GRAPH_ADAPTER!r}."
        )
    return ApplicationService(native, selected)


# Modules an `engine.config.application` path may import from. Fixed here, never read from the
# manifest: a manifest that names both the code and the allow-list for it would defeat the list.
# Operators extend it through the environment, which the manifest author does not control.
_APPLICATION_MODULE_PREFIXES = ("examples.",)
_APPLICATION_PREFIXES_ENV = "MRAG_APPLICATION_MODULE_PREFIXES"


def _application_prefixes() -> tuple[str, ...]:
    extra = tuple(
        prefix.strip()
        for prefix in os.environ.get(_APPLICATION_PREFIXES_ENV, "").split(",")
        if prefix.strip()
    )
    return (*_APPLICATION_MODULE_PREFIXES, *extra)


def _load_existing_graph_adapter(
    manifest: PipelineManifest, container: Container
) -> DocumentEngine:
    """The single explicit existing-application branch (ADR-0018 §14) and its profile gate.

    Imports the wrapped application from an allow-listed `module:callable`, resolves the
    adapter's `ApplicationProfile`, caps the wired evidence by the profile's ceiling and refuses
    to return the adapter when `assurance.min_level` is out of reach — all before any request.
    """
    from modular_rag.adapters.applications.existing_graph import (
        ApplicationHandle,
        ExistingGraphApplicationAdapter,
    )

    config = manifest.engine.config if manifest.engine else {}
    target = config.get("application")
    if not isinstance(target, str) or target.count(":") != 1:
        raise ConfigurationError(
            "engine.config.application must be a 'module:callable' path for "
            f"engine.adapter={EXISTING_GRAPH_ADAPTER!r}"
        )
    module_name, attribute = target.split(":")
    prefixes = _application_prefixes()
    if not any(module_name.startswith(prefix) for prefix in prefixes):
        raise ConfigurationError(
            f"engine.config.application module {module_name!r} is not in the allowed prefixes "
            f"{list(prefixes)}; extend {_APPLICATION_PREFIXES_ENV} to allow it"
        )
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise ConfigurationError(f"Cannot load application {target!r}: {exc}") from exc
    application = factory()
    if not isinstance(application, ApplicationHandle):
        raise ConfigurationError(
            f"{target!r} did not return an object satisfying ApplicationHandle"
        )

    adapter = ExistingGraphApplicationAdapter(
        application,
        container,
        egress_provider=str(config.get("egress_provider", manifest.generator.type)),
    )
    if not isinstance(adapter, ApplicationProfileProvider):
        raise ConfigurationError(
            f"engine.adapter={EXISTING_GRAPH_ADAPTER!r} must expose an ApplicationProfile"
        )
    error = application_assurance_error(
        container,
        EXISTING_GRAPH_ADAPTER,
        evidence_ceiling(adapter.application_profile),
        manifest.assurance.min_level if manifest.assurance else None,
    )
    if error is not None:
        raise ConfigurationError(error)
    return adapter


def _raise_for_manifest_errors(
    manifest: PipelineManifest, registry: ComponentRegistry
) -> None:
    """Fail startup before constructing components when activation is invalid."""
    errors = validate_capabilities(manifest, registry)
    if errors:
        raise ConfigurationError("Invalid runtime manifest: " + "; ".join(errors))
