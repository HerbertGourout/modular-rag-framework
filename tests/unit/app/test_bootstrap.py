"""Characterization tests for app/bootstrap.py: manifest loading and pipeline wiring.

Lot 4 (docs/refactoring-plan.md).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from modular_rag.app.bootstrap import load_manifest, load_pipeline
from modular_rag.core.errors import ManifestError
from modular_rag.orchestration.engine import RAGEngine


def test_load_manifest_raises_manifest_error_when_file_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"

    with pytest.raises(ManifestError, match="Manifest not found"):
        load_manifest(missing)


def test_load_manifest_raises_manifest_error_on_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("chunker: [this is not: valid: yaml", encoding="utf-8")

    with pytest.raises(ManifestError, match="Invalid YAML"):
        load_manifest(bad)


def test_load_manifest_validates_against_pipeline_manifest_schema(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("id: my-pipeline\n", encoding="utf-8")

    manifest = load_manifest(manifest_file)

    assert manifest.id == "my-pipeline"
    assert manifest.chunker.type == "adaptive"  # documented default
    assert manifest.tenant == "default"


def test_load_pipeline_wires_the_default_registry_and_returns_a_rag_engine(
    tmp_path: Path,
) -> None:
    """Exercises ComponentRegistry.default() end to end via built-in adapter type
    names. Safe as a unit test: every adapter here lazy-loads its heavy dependency
    (sentence-transformers model, qdrant-client connection, OpenAI client) on first
    *use*, not at construction — confirmed by reading each adapter's __init__
    before writing this test. No network/model I/O happens.
    """
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        "id: my-pipeline\n"
        "chunker:\n  type: fixed\n  config:\n    chunk_size: 100\n"
        "embedder:\n  type: sentence-transformers\n  config: {}\n"
        "indexer:\n  type: qdrant\n  config: {}\n"
        "retriever:\n  type: vector\n  config: {}\n"
        "generator:\n  type: openai\n  config: {}\n",
        encoding="utf-8",
    )

    pipeline = load_pipeline(manifest_file)

    assert isinstance(pipeline, RAGEngine)
    # Characterizes the private-container access pattern also used by api/ and
    # cli/ — there is no public accessor for the wired manifest today.
    assert pipeline._c.manifest.id == "my-pipeline"
