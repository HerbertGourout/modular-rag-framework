"""Contract conformance tests for Generator implementations.

Note: both generators lazily load their API client, so Protocol conformance
is testable without the openai/anthropic packages or API keys. Generation
behaviour is covered in tests/unit/generation/synthesizers/.
"""
from __future__ import annotations

import pytest

from modular_rag.contracts.generation import Generator
from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator
from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator

GENERATORS = [OpenAIGenerator(), AnthropicGenerator()]


@pytest.mark.parametrize("generator", GENERATORS, ids=lambda g: type(g).__name__)
def test_implements_generator_protocol(generator):
    assert isinstance(generator, Generator)


@pytest.mark.parametrize("generator", GENERATORS, ids=lambda g: type(g).__name__)
def test_name_returns_non_empty_string(generator):
    assert isinstance(generator.name(), str)
    assert len(generator.name()) > 0


def test_generator_names_are_unique():
    names = [g.name() for g in GENERATORS]
    assert len(names) == len(set(names))
