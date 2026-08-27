"""Unit tests for core/pricing.py (Lot 12, external plan — "Metrics,
Dashboards, and SLO")."""
from __future__ import annotations

from modular_rag.core.pricing import estimate_cost_usd, known_models


def test_estimate_cost_usd_for_a_known_model() -> None:
    cost = estimate_cost_usd("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)

    assert cost == 0.15 + 0.60


def test_estimate_cost_usd_scales_linearly_with_token_count() -> None:
    cost = estimate_cost_usd("gpt-4o-mini", input_tokens=500_000, output_tokens=0)

    assert cost == 0.075


def test_estimate_cost_usd_returns_none_for_an_unknown_model() -> None:
    """Never fabricate a price for a model this table doesn't recognize —
    `None` means "cost unavailable," not zero."""
    assert estimate_cost_usd("some-future-model-not-in-the-table", 100, 100) is None


def test_estimate_cost_usd_returns_zero_for_zero_tokens_on_a_known_model() -> None:
    assert estimate_cost_usd("gpt-4o-mini", 0, 0) == 0.0


def test_known_models_is_non_empty_and_matches_the_generators_default_models() -> None:
    """Cross-check against the actual default `model` values the two real
    generators ship with, so this table can't silently drift out of sync
    with what production traffic will actually ask it to price."""
    from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator
    from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator

    models = known_models()
    assert models
    assert OpenAIGenerator().model in models
    assert AnthropicGenerator().model in models
