"""Contract conformance tests for Embedder implementations.

No prior conformance coverage existed for `contracts.embeddings.Embedder` at
all (Lot 4, secure preset e2e correction — found while adding
`DeterministicEmbedder`). All three implementations construct without
network/model I/O: `HuggingFaceEmbedder` here uses a model name present in
its static `_DIMENSIONS` table (ADR-0009) so `.dimensions` is free too;
`OpenAIEmbedder` and `DeterministicEmbedder` never touch the network for
construction, `.dimensions`, or `.name()` either. `embed()`/`aembed()`
behaviour needing a real model or API key is covered in
tests/unit/adapters/embeddings/ instead.
"""
from __future__ import annotations

import pytest

from modular_rag.adapters.embeddings.deterministic_embedder import DeterministicEmbedder
from modular_rag.adapters.embeddings.hf_embedder import HuggingFaceEmbedder
from modular_rag.adapters.embeddings.openai_embedder import OpenAIEmbedder
from modular_rag.contracts.embeddings import Embedder

EMBEDDERS = [
    HuggingFaceEmbedder(model="BAAI/bge-small-en-v1.5"),
    OpenAIEmbedder(),
    DeterministicEmbedder(),
]


@pytest.mark.parametrize("embedder", EMBEDDERS, ids=lambda e: type(e).__name__)
def test_implements_embedder_protocol(embedder):
    assert isinstance(embedder, Embedder)


@pytest.mark.parametrize("embedder", EMBEDDERS, ids=lambda e: type(e).__name__)
def test_name_returns_non_empty_string(embedder):
    assert isinstance(embedder.name(), str)
    assert len(embedder.name()) > 0


@pytest.mark.parametrize("embedder", EMBEDDERS, ids=lambda e: type(e).__name__)
def test_dimensions_is_a_positive_int(embedder):
    assert isinstance(embedder.dimensions, int)
    assert embedder.dimensions > 0
