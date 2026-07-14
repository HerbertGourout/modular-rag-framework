"""Contract conformance tests for Reranker implementations.

Note: CrossEncoderReranker lazily loads its sentence-transformers model, so
Protocol conformance and the empty-input path are testable without the model.
Scoring behaviour is covered in tests/unit/retrieval/rerankers/.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.reranking import Reranker
from modular_rag.core.models.query import Query
from modular_rag.retrieval.rerankers.cross_encoder import CrossEncoderReranker

RERANKERS = [CrossEncoderReranker()]


@pytest.mark.parametrize("reranker", RERANKERS, ids=lambda r: type(r).__name__)
def test_implements_reranker_protocol(reranker):
    assert isinstance(reranker, Reranker)


@pytest.mark.parametrize("reranker", RERANKERS, ids=lambda r: type(r).__name__)
def test_name_returns_non_empty_string(reranker):
    assert isinstance(reranker.name(), str)
    assert len(reranker.name()) > 0


@pytest.mark.parametrize("reranker", RERANKERS, ids=lambda r: type(r).__name__)
def test_rerank_empty_input_returns_empty_list(reranker):
    result = reranker.rerank(Query(text="anything"), [], k=5)
    assert result == []
