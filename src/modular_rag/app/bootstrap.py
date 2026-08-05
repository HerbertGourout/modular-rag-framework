from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.core.errors import ConfigurationError, ManifestError
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter
from modular_rag.orchestration.registry import ComponentRegistry

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
    — existing callers (API, CLI, examples/simple_qa/) keep working against
    the concrete `RAGEngine` unchanged. Prefer `load_native_engine()` for new
    code that wants the engine-neutral `DocumentEngine` port instead.
    """
    manifest = load_manifest(path)
    registry = ComponentRegistry.default()
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
    manifest = load_manifest(path)
    registry = ComponentRegistry.default()
    container = registry.wire(manifest)
    adapter_name = manifest.engine.adapter if manifest.engine else "native"

    if adapter_name == "native":
        return NativeEngineAdapter(RAGEngine(container))
    if adapter_name == "langgraph":
        from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter

        return LangGraphEngineAdapter(container)
    raise ConfigurationError(
        f"Unknown engine.adapter {adapter_name!r} in manifest {path!r}. "
        f"Expected 'native' or 'langgraph'."
    )
