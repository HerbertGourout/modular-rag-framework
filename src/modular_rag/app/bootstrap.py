from __future__ import annotations

from pathlib import Path

import yaml

from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.core.errors import ManifestError
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter
from modular_rag.orchestration.registry import ComponentRegistry


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
