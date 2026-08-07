"""Unit tests for the complete top-level dependency policy."""

from __future__ import annotations

import pytest
from scripts.check_layering import _violation_reason


@pytest.mark.parametrize(
    ("importer", "imported"),
    [
        ("core", "modular_rag.core.models"),
        ("contracts", "modular_rag.core.models"),
        ("contracts", "modular_rag.contracts.engine"),
        ("retrieval", "modular_rag.core.models"),
        ("retrieval", "modular_rag.contracts.retrieval"),
        ("retrieval", "modular_rag.retrieval.fusion"),
        ("adapters", "modular_rag.contracts.engine"),
        ("adapters", "modular_rag.adapters.llms"),
        ("orchestration", "modular_rag.contracts.engine"),
        ("orchestration", "modular_rag.orchestration.registry"),
        ("app", "modular_rag.orchestration.engine"),
        ("app", "modular_rag.contracts.manifests"),
        ("app", "modular_rag.adapters.llms.langgraph_engine"),
        ("app", "modular_rag.ingestion.chunkers.fixed"),
        ("api", "modular_rag.app.bootstrap"),
        ("api", "modular_rag.api.errors"),
        ("cli", "modular_rag.app.bootstrap"),
        ("cli", "modular_rag.cli.helpers"),
    ],
)
def test_allowed_dependency_returns_no_violation(importer: str, imported: str) -> None:
    assert _violation_reason(importer, imported) is None


@pytest.mark.parametrize(
    ("importer", "imported", "message"),
    [
        ("core", "modular_rag.contracts.engine", "core can only import core modules"),
        (
            "contracts",
            "modular_rag.security.filters",
            "contracts can only import core or contracts modules",
        ),
        (
            "retrieval",
            "modular_rag.generation.synthesizers",
            "domain modules cannot import other domain modules",
        ),
        (
            "adapters",
            "modular_rag.retrieval.retrievers",
            "adapters cannot import domain modules",
        ),
        (
            "orchestration",
            "modular_rag.app.container",
            "orchestration can only import core, contracts, or orchestration modules",
        ),
        (
            "app",
            "modular_rag.api",
            "app cannot import api, cli, or unknown project layers",
        ),
        (
            "api",
            "modular_rag.contracts.identity",
            "api and cli can only import app or their own interface package",
        ),
        (
            "cli",
            "modular_rag.ingestion.pipelines",
            "api and cli can only import app or their own interface package",
        ),
    ],
)
def test_forbidden_dependency_returns_specific_reason(
    importer: str, imported: str, message: str
) -> None:
    assert _violation_reason(importer, imported) == message


def test_external_dependency_is_outside_the_project_policy() -> None:
    assert _violation_reason("api", "fastapi") is None
