"""Fixture-validity check for tests/fixtures/data_classification/sample_documents.yaml
(Lot 11a, docs/refactoring-plan.md — "paper-and-fixture deliverable; no enforcement
code yet"). This validates the *fixture's own shape*, not any enforcement behavior —
there is no enforcement to test yet (that's Lot 11b/11c).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from modular_rag.core.enums import DataClassification, PIICategory

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "data_classification" / "sample_documents.yaml"
)


@pytest.fixture()
def documents() -> list[dict]:
    data = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["documents"]


def test_fixture_file_exists_and_is_non_empty(documents: list[dict]) -> None:
    assert len(documents) > 0


def test_every_document_has_a_valid_classification(documents: list[dict]) -> None:
    valid = {c.value for c in DataClassification}
    for doc in documents:
        assert doc["classification"] in valid, doc["id"]


def test_every_document_pii_category_is_a_known_category(documents: list[dict]) -> None:
    valid = {c.value for c in PIICategory}
    for doc in documents:
        for category in doc.get("pii_categories", []):
            assert category in valid, (doc["id"], category)


def test_restricted_documents_declare_at_least_one_pii_category(documents: list[dict]) -> None:
    """Fixture-schema invariant documented in the fixture file's own header comment:
    a `restricted` entry must justify the level with at least one PII category."""
    for doc in documents:
        if doc["classification"] == DataClassification.RESTRICTED.value:
            assert doc["pii_categories"], doc["id"]


def test_all_classification_levels_are_represented(documents: list[dict]) -> None:
    seen = {doc["classification"] for doc in documents}
    assert seen == {c.value for c in DataClassification}


def test_every_document_has_a_tenant_id_and_rationale(documents: list[dict]) -> None:
    for doc in documents:
        assert doc["tenant_id"]
        assert doc["rationale"].strip()


def test_fixture_includes_a_cross_tenant_example() -> None:
    """Lot 11b's tenant-isolation tests need at least two distinct tenant_id values
    to test cross-tenant denial against."""
    data = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    tenants = {doc["tenant_id"] for doc in data["documents"]}
    assert len(tenants) >= 2
