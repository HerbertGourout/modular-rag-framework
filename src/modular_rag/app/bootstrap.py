from __future__ import annotations

from pathlib import Path

import yaml

from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.core.errors import ManifestError
from modular_rag.orchestration.engine import RAGEngine
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
    """Load a manifest and return a ready-to-use RAGEngine."""
    manifest = load_manifest(path)
    registry = ComponentRegistry.default()
    container = registry.wire(manifest)
    return RAGEngine(container)
