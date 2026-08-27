"""Static, approximate LLM pricing table (Lot 12 — external plan, "Metrics,
Dashboards, and SLO").

Not live-fetched from any provider API — a hardcoded, manually-refreshed
table. A live pricing lookup would add network I/O and a new external
dependency to every generation call, contradicting this codebase's existing
lazy/cheap-instrumentation posture (`.claude/rules/adapters.md`'s lazy-import
discipline exists for the same reason: keep the hot path free of avoidable
external calls). Prices are USD per 1,000,000 tokens.

Model coverage is deliberately anchored to what this codebase's own
generators and manifests actually reference (`generation/synthesizers/
openai_gen.py`'s/`anthropic_gen.py`'s own `model` defaults, and every
`model:` value across `manifests/presets/`/`manifests/blueprints/`), checked
directly rather than assumed — `tests/unit/core/test_pricing.py` cross-checks
this table against both generators' real default `model` values so this list
can't silently drift out of sync with what production traffic actually asks
it to price. `gpt-4o`/`gpt-4o-mini` prices are sourced from OpenAI's own
public pricing page as of 2026-08 — treat as approximate and re-verify before
using for real billing/chargeback decisions. `claude-opus-4-7` (this
codebase's own `AnthropicGenerator` default and `manifests/blueprints/
multimodal-rag.yaml`'s only referenced Claude model) has no public rate card
this table's author could find — its price below is a placeholder
extrapolation from Anthropic's Opus-tier pricing history, explicitly flagged
as such, not a verified published rate; re-verify before relying on it for
anything beyond rough relative-cost comparison.

`docs/research/`'s curated arXiv digests have no coverage of LLM pricing (a
commercial/operational fact, not a research topic) — there is no citation to
back these numbers beyond the providers' own published rate cards (where one
exists), and none is claimed.
"""
from __future__ import annotations

# model identifier -> (input price per 1M tokens USD, output price per 1M tokens USD)
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    # Placeholder extrapolation, not a verified published rate -- see the
    # module docstring above.
    "claude-opus-4-7": (15.00, 75.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return an approximate USD cost for one generation call, or `None` for
    a model this table does not recognize — never fabricate a price for an
    unknown model. Callers (`generation/synthesizers/*.py`) treat `None` as
    "cost unavailable," not as zero.
    """
    prices = _PRICE_TABLE.get(model)
    if prices is None:
        return None
    input_price_per_1m, output_price_per_1m = prices
    return (input_tokens / 1_000_000) * input_price_per_1m + (
        output_tokens / 1_000_000
    ) * output_price_per_1m


def known_models() -> frozenset[str]:
    """Models this table has a price for — used by tests and by
    `docs/observability/` to keep the reference dashboard's cost panel
    documentation in sync with what can actually be priced."""
    return frozenset(_PRICE_TABLE)
