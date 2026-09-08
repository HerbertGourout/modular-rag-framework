"""Unit tests for core/enums.py's Lot 20 additions —
classification_rank()/combined_classification() (docs/refactoring-plan.md,
"Data Classification and LLM Egress Control")."""
from __future__ import annotations

from modular_rag.core.enums import DataClassification, classification_rank, combined_classification


def test_classification_rank_is_strictly_increasing_by_sensitivity():
    ranks = [classification_rank(level) for level in DataClassification]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)  # no ties


def test_classification_rank_public_is_lowest():
    assert classification_rank(DataClassification.PUBLIC) < classification_rank(
        DataClassification.RESTRICTED
    )


def test_combined_classification_of_empty_input_is_none():
    assert combined_classification([]) is None


def test_combined_classification_of_all_none_is_none():
    assert combined_classification([None, None]) is None


def test_combined_classification_any_none_makes_the_whole_result_none():
    """A restricted item next to an unlabeled one must not silently average
    out to something less restrictive than 'unknown'."""
    result = combined_classification([DataClassification.RESTRICTED, None])
    assert result is None


def test_combined_classification_returns_the_most_restrictive_value():
    result = combined_classification(
        [DataClassification.PUBLIC, DataClassification.CONFIDENTIAL, DataClassification.INTERNAL]
    )
    assert result is DataClassification.CONFIDENTIAL


def test_combined_classification_single_value_passthrough():
    assert combined_classification([DataClassification.RESTRICTED]) is DataClassification.RESTRICTED
