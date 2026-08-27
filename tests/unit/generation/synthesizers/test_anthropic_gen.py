"""Unit tests for AnthropicGenerator.

Injects a fake client on `_client` so the tests exercise the generator's own
logic (prompt building, TraceStep emission, Answer assembly) without the
anthropic package or an API key.
"""
from __future__ import annotations

from types import SimpleNamespace

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace
from modular_rag.generation.synthesizers.anthropic_gen import AnthropicGenerator


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict = {}

    def create(self, **kwargs) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(text=self._text)],
            usage=SimpleNamespace(input_tokens=21, output_tokens=43),
        )


def _fake_client(text: str = "Grounded answer.") -> SimpleNamespace:
    return SimpleNamespace(messages=_FakeMessages(text))


def _context(contents: list[str]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk=Chunk(doc_id=new_id(), content=c, metadata={"source": f"doc{i}.txt"}),
            score=0.9,
            rank=i,
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for i, c in enumerate(contents, 1)
    ]


def _generate(generator: AnthropicGenerator, contents: list[str]):
    query = Query(text="What is RAG?")
    trace = Trace(query_id=query.id)
    answer = generator.generate(query, _context(contents), trace)
    return query, trace, answer


def test_client_is_not_loaded_at_init():
    assert AnthropicGenerator()._client is None


def test_answer_carries_text_model_and_query_id():
    generator = AnthropicGenerator(model="claude-sonnet-5")
    generator._client = _fake_client("RAG combines retrieval and generation.")

    query, _, answer = _generate(generator, ["RAG combines retrieval and generation."])

    assert answer.text == "RAG combines retrieval and generation."
    assert answer.model == "claude-sonnet-5"
    assert answer.query_id == query.id


def test_low_support_answer_becomes_refusal():
    generator = AnthropicGenerator(model="claude-sonnet-5")
    generator._client = _fake_client("bananas oranges kiwis")

    _, _, answer = _generate(generator, ["RAG combines retrieval and generation."])

    assert answer.text == "I don't know based on the provided context."
    assert answer.citations == []
    assert answer.confidence == 0.0


def test_one_citation_per_context_chunk():
    generator = AnthropicGenerator()
    generator._client = _fake_client("chunk one chunk two")

    _, _, answer = _generate(generator, ["chunk one", "chunk two"])

    assert len(answer.citations) == 2
    assert [c.source for c in answer.citations] == ["doc1.txt", "doc2.txt"]


def test_trace_step_records_token_usage_and_model():
    generator = AnthropicGenerator(model="claude-sonnet-5")
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "anthropic_generate"]
    assert len(steps) == 1
    assert steps[0].input_tokens == 21
    assert steps[0].output_tokens == 43
    assert steps[0].metadata["model"] == "claude-sonnet-5"
    assert steps[0].latency_ms >= 0


def test_trace_step_records_cost_usd_for_the_default_priced_model():
    """Lot 12 (external plan — "Metrics, Dashboards, and SLO"): the
    generator's own default model (`claude-opus-4-7`, this file's `_generate`
    helper's implicit default via `AnthropicGenerator()`) is the one Claude
    model `core.pricing` actually has a price for — see that module's own
    docstring on why."""
    from modular_rag.core.pricing import estimate_cost_usd

    generator = AnthropicGenerator()  # default model: claude-opus-4-7
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "anthropic_generate"]
    expected = estimate_cost_usd("claude-opus-4-7", 21, 43)
    assert steps[0].metadata["cost_usd"] == expected
    assert expected is not None and expected > 0


def test_trace_step_omits_cost_usd_for_an_unpriced_model():
    """`claude-sonnet-5` (used elsewhere in this file) isn't in
    `core.pricing`'s table -- the field must be absent, never fabricated
    as 0.0."""
    generator = AnthropicGenerator(model="claude-sonnet-5")
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "anthropic_generate"]
    assert "cost_usd" not in steps[0].metadata


def test_prompt_contains_numbered_sources_and_question():
    generator = AnthropicGenerator()
    client = _fake_client()
    generator._client = client

    _generate(generator, ["first passage", "second passage"])

    sent = client.messages.last_kwargs
    user_message = sent["messages"][0]["content"]
    assert "[1] doc1.txt\nfirst passage" in user_message
    assert "[2] doc2.txt\nsecond passage" in user_message
    assert "Question: What is RAG?" in user_message


def test_system_prompt_carries_negative_rejection_clause():
    # arXiv:2404.10981 §7.1 — decline to answer when context lacks the answer.
    generator = AnthropicGenerator()
    client = _fake_client()
    generator._client = client

    _generate(generator, ["some context"])

    system_prompt = client.messages.last_kwargs["system"]
    assert system_prompt.split("\n", 1)[0].startswith("You are a precise assistant")
    assert "does not contain the answer" in system_prompt
    assert "do not guess" in system_prompt


def test_generation_params_are_passed_to_api():
    generator = AnthropicGenerator(model="claude-haiku-4-5-20251001", max_tokens=256)
    client = _fake_client()
    generator._client = client

    _generate(generator, ["ctx"])

    sent = client.messages.last_kwargs
    assert sent["model"] == "claude-haiku-4-5-20251001"
    assert sent["max_tokens"] == 256
    assert "system" in sent


def test_name_is_stable_identifier():
    assert AnthropicGenerator().name() == "anthropic"


def test_default_timeout_is_thirty_seconds():
    assert AnthropicGenerator().timeout == 30.0


def test_get_client_passes_timeout_to_the_real_anthropic_client():
    """Lot 14 (docs/refactoring-plan.md — "timeouts"): constructs the real
    `anthropic.Anthropic` client (no network call at construction time) and
    checks its own `.timeout` attribute."""
    generator = AnthropicGenerator(api_key="sk-test", timeout=5.0)

    client = generator._get_client()

    assert client.timeout == 5.0


def test_close_releases_the_client_if_one_was_opened():
    generator = AnthropicGenerator(api_key="sk-test")
    generator._get_client()
    assert generator._client is not None

    generator.close()

    assert generator._client is None


def test_close_is_a_no_op_when_no_client_was_ever_opened():
    AnthropicGenerator().close()  # must not raise


# ---------------------------------------------------------------------------
# Codex review HIGH-001/HIGH-002/HIGH-003/HIGH-004 (Lot 6) — check_health().
# No generator originally implemented HealthCheckable at all (second pass);
# the third pass replaced a credential-presence check with a real,
# authenticated, non-generative call, since a merely-present (but invalid)
# key previously reported healthy (verified live). The fourth pass fixed two
# remaining gaps: the probe used `client.models.list()` and discarded the
# result (HIGH-004) — switched to `client.models.retrieve(self.model)`; and
# the probe inherited the shared client's 30s timeout and the SDK's default
# `max_retries=2` (HIGH-002) — switched to `client.with_options(...)`, and
# `self._health_lock` is now acquired with a bound too.
# ---------------------------------------------------------------------------


class _FakeModels:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail
        self.retrieve_calls: list[str] = []

    def retrieve(self, model: str) -> SimpleNamespace:
        self.retrieve_calls.append(model)
        if self._should_fail:
            raise RuntimeError("API key is invalid")
        return SimpleNamespace(id=model)


class _FakeHealthClient:
    """See `test_openai_gen.py`'s identical fake for the full rationale."""

    def __init__(self, should_fail: bool = False) -> None:
        self.models = _FakeModels(should_fail=should_fail)
        self.with_options_calls: list[dict] = []

    def with_options(self, **kwargs) -> _FakeHealthClient:
        self.with_options_calls.append(kwargs)
        return self


def _fake_health_client(should_fail: bool = False) -> _FakeHealthClient:
    return _FakeHealthClient(should_fail=should_fail)


def test_check_health_is_healthy_when_the_provider_call_succeeds():
    generator = AnthropicGenerator()
    generator._client = _fake_health_client()

    results = generator.check_health()

    assert results[0].name == "anthropic"
    assert results[0].healthy is True


def test_check_health_is_unhealthy_when_the_provider_call_fails():
    """Codex review HIGH-003 (Lot 6, third pass): a credential-presence
    check cannot catch a revoked/malformed/expired/over-quota key — a real
    call must actually be attempted and its failure surfaced."""
    generator = AnthropicGenerator()
    generator._client = _fake_health_client(should_fail=True)

    results = generator.check_health()

    assert results[0].healthy is False


def test_check_health_validates_the_specific_configured_model():
    """Codex review HIGH-004 (Lot 6, fourth pass): `models.list()`'s result
    was previously discarded — `models.retrieve()` must be called with
    exactly the configured model."""
    generator = AnthropicGenerator(model="claude-custom")
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()

    assert fake.models.retrieve_calls == ["claude-custom"]


def test_check_health_uses_a_short_bounded_probe_timeout_with_no_retries():
    """Codex review HIGH-002 (Lot 6, fourth pass): see
    `test_openai_gen.py`'s identical test for the full rationale."""
    import modular_rag.generation.synthesizers.anthropic_gen as module

    generator = AnthropicGenerator(timeout=30.0)
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()

    assert fake.with_options_calls == [
        {"timeout": module._HEALTH_CHECK_TIMEOUT, "max_retries": 0}
    ]
    assert module._HEALTH_CHECK_TIMEOUT < generator.timeout


def test_check_health_reports_busy_when_the_lock_cannot_be_acquired(monkeypatch):
    """Codex review HIGH-002 (Lot 6, fourth pass): see
    `test_openai_gen.py`'s identical test for the full rationale."""
    generator = AnthropicGenerator()
    generator._health_lock.acquire()
    import modular_rag.generation.synthesizers.anthropic_gen as module

    monkeypatch.setattr(module, "_HEALTH_LOCK_ACQUIRE_TIMEOUT", 0.05)

    results = generator.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "busy"


def test_check_health_caches_a_healthy_result_so_repeated_calls_dont_reach_the_provider():
    generator = AnthropicGenerator()
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()
    generator.check_health()

    assert len(fake.models.retrieve_calls) == 1


def test_check_health_refreshes_once_the_cache_ttl_has_elapsed(monkeypatch):
    import modular_rag.generation.synthesizers.anthropic_gen as module

    clock = {"now": 0.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])
    generator = AnthropicGenerator()
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()
    clock["now"] += module._HEALTH_CHECK_CACHE_SECONDS + 1
    generator.check_health()

    assert len(fake.models.retrieve_calls) == 2
