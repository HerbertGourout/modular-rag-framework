"""Unit tests for OpenAIGenerator.

Injects a fake client on `_client` so the tests exercise the generator's own
logic (prompt building, TraceStep emission, Answer assembly) without the
openai package or an API key.
"""
from __future__ import annotations

from types import SimpleNamespace

from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace
from modular_rag.generation.synthesizers.openai_gen import OpenAIGenerator


class _FakeCompletions:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict = {}

    def create(self, **kwargs) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._text))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34, total_tokens=46),
        )


def _fake_client(text: str = "Grounded answer.") -> SimpleNamespace:
    completions = _FakeCompletions(text)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _context(contents: list[str]) -> list[RetrievedChunk]:
    from modular_rag.core.enums import RetrievalMethod

    return [
        RetrievedChunk(
            chunk=Chunk(doc_id=new_id(), content=c, metadata={"source": f"doc{i}.txt"}),
            score=0.9,
            rank=i,
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for i, c in enumerate(contents, 1)
    ]


def _generate(generator: OpenAIGenerator, contents: list[str]):
    query = Query(text="What is RAG?")
    trace = Trace(query_id=query.id)
    answer = generator.generate(query, _context(contents), trace)
    return query, trace, answer


def test_client_is_not_loaded_at_init():
    assert OpenAIGenerator()._client is None


def test_answer_carries_text_model_and_query_id():
    generator = OpenAIGenerator(model="gpt-4o-mini")
    generator._client = _fake_client("RAG combines retrieval and generation.")

    query, _, answer = _generate(generator, ["RAG combines retrieval and generation."])

    assert answer.text == "RAG combines retrieval and generation."
    assert answer.model == "gpt-4o-mini"
    assert answer.query_id == query.id


def test_low_support_answer_becomes_refusal():
    generator = OpenAIGenerator(model="gpt-4o-mini")
    generator._client = _fake_client("bananas oranges kiwis")

    _, _, answer = _generate(generator, ["RAG combines retrieval and generation."])

    assert answer.text == "I don't know based on the provided context."
    assert answer.citations == []
    assert answer.confidence == 0.0


def test_one_citation_per_context_chunk():
    generator = OpenAIGenerator()
    generator._client = _fake_client("chunk one chunk two")

    _, _, answer = _generate(generator, ["chunk one", "chunk two"])

    assert len(answer.citations) == 2
    assert [c.source for c in answer.citations] == ["doc1.txt", "doc2.txt"]


def test_trace_step_records_token_usage_and_model():
    generator = OpenAIGenerator(model="gpt-4o-mini")
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "openai_generate"]
    assert len(steps) == 1
    assert steps[0].input_tokens == 12
    assert steps[0].output_tokens == 34
    assert steps[0].metadata["model"] == "gpt-4o-mini"
    assert steps[0].latency_ms >= 0


def test_trace_step_records_cost_usd_for_a_priced_model():
    """Lot 12 (external plan — "Metrics, Dashboards, and SLO"): cost is
    computed from `core.pricing.estimate_cost_usd()` and attached to the
    same TraceStep metadata the tokens/model already live in — this is what
    `orchestration/engine.py` reads to emit `mrag.generation.cost_usd`."""
    from modular_rag.core.pricing import estimate_cost_usd

    generator = OpenAIGenerator(model="gpt-4o-mini")
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "openai_generate"]
    expected = estimate_cost_usd("gpt-4o-mini", 12, 34)
    assert steps[0].metadata["cost_usd"] == expected
    assert expected is not None and expected > 0


def test_trace_step_omits_cost_usd_for_an_unpriced_model():
    """Never fabricate a cost for a model `core.pricing` doesn't recognize —
    the field is absent entirely, not set to 0.0."""
    generator = OpenAIGenerator(model="some-future-model-not-in-the-price-table")
    generator._client = _fake_client()

    _, trace, _ = _generate(generator, ["some context"])

    steps = [s for s in trace.steps if s.name == "openai_generate"]
    assert "cost_usd" not in steps[0].metadata


def test_prompt_contains_numbered_sources_and_question():
    generator = OpenAIGenerator()
    client = _fake_client()
    generator._client = client

    _generate(generator, ["first passage", "second passage"])

    sent = client.chat.completions.last_kwargs
    user_message = sent["messages"][1]["content"]
    assert "[1] Source: doc1.txt\nfirst passage" in user_message
    assert "[2] Source: doc2.txt\nsecond passage" in user_message
    assert "Question: What is RAG?" in user_message


def test_system_prompt_carries_negative_rejection_clause():
    # arXiv:2404.10981 §7.1 — decline to answer when context lacks the answer.
    generator = OpenAIGenerator()
    client = _fake_client()
    generator._client = client

    _generate(generator, ["some context"])

    system_message = client.chat.completions.last_kwargs["messages"][0]["content"]
    assert system_message.split("\n", 1)[0].startswith("You are a precise assistant")
    assert "does not contain the answer" in system_message
    assert "do not guess" in system_message


def test_generation_params_are_passed_to_api():
    generator = OpenAIGenerator(model="gpt-4o", temperature=0.5, max_tokens=128)
    client = _fake_client()
    generator._client = client

    _generate(generator, ["ctx"])

    sent = client.chat.completions.last_kwargs
    assert sent["model"] == "gpt-4o"
    assert sent["temperature"] == 0.5
    assert sent["max_tokens"] == 128


def test_none_content_becomes_empty_answer_text():
    generator = OpenAIGenerator()
    generator._client = _fake_client(text=None)

    _, _, answer = _generate(generator, ["ctx"])

    assert answer.text == "I don't know based on the provided context."
    assert answer.citations == []
    assert answer.confidence == 0.0


def test_name_is_stable_identifier():
    assert OpenAIGenerator().name() == "openai"


def test_default_timeout_is_thirty_seconds():
    assert OpenAIGenerator().timeout == 30.0


def test_get_client_passes_timeout_to_the_real_openai_client():
    """Lot 14 (docs/refactoring-plan.md — "timeouts"): constructs the real
    `openai.OpenAI` client (no network call happens at construction time)
    and checks its own `.timeout` attribute — proof the kwarg is accepted
    and actually reaches the SDK, not just stored on this wrapper."""
    generator = OpenAIGenerator(api_key="sk-test", timeout=5.0)

    client = generator._get_client()

    assert client.timeout == 5.0


def test_close_releases_the_client_if_one_was_opened():
    generator = OpenAIGenerator(api_key="sk-test")
    generator._get_client()
    assert generator._client is not None

    generator.close()

    assert generator._client is None


def test_close_is_a_no_op_when_no_client_was_ever_opened():
    OpenAIGenerator().close()  # must not raise


# ---------------------------------------------------------------------------
# Codex review HIGH-001/HIGH-002/HIGH-003/HIGH-004 (Lot 6) — check_health().
# No generator originally implemented HealthCheckable at all (second pass);
# the third pass replaced a client-construction-only check with a real,
# authenticated, non-generative call, since a credential-presence check
# reported healthy for a deliberately invalid key (verified live). The
# fourth pass fixed two remaining gaps: the probe call used
# `client.models.list()` and discarded the result, so a valid key for *any*
# model reported healthy even if `self.model` itself was misspelled or
# inaccessible (HIGH-004) — switched to `client.models.retrieve(self.model)`;
# and the probe went through the shared client unmodified, inheriting the
# 30s production timeout and the SDK's default `max_retries=2` (HIGH-002) —
# switched to `client.with_options(timeout=..., max_retries=0)`, and
# `self._health_lock` is now acquired with a bound too.
# ---------------------------------------------------------------------------


class _FakeModels:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail
        self.retrieve_calls: list[str] = []

    def retrieve(self, model: str) -> SimpleNamespace:
        self.retrieve_calls.append(model)
        if self._should_fail:
            raise RuntimeError("Incorrect API key provided")
        return SimpleNamespace(id=model)


class _FakeHealthClient:
    """`with_options()` returns `self` (not a fresh object) so a test can
    still observe `.models.retrieve_calls` through the same reference the
    generator holds, while also recording the options each call passed —
    proving HIGH-002's timeout/retry override actually reaches the SDK
    call site."""

    def __init__(self, should_fail: bool = False) -> None:
        self.models = _FakeModels(should_fail=should_fail)
        self.with_options_calls: list[dict] = []

    def with_options(self, **kwargs) -> _FakeHealthClient:
        self.with_options_calls.append(kwargs)
        return self


def _fake_health_client(should_fail: bool = False) -> _FakeHealthClient:
    return _FakeHealthClient(should_fail=should_fail)


def test_check_health_is_healthy_when_the_provider_call_succeeds():
    generator = OpenAIGenerator()
    generator._client = _fake_health_client()

    results = generator.check_health()

    assert results[0].name == "openai"
    assert results[0].healthy is True


def test_check_health_is_unhealthy_when_the_provider_call_fails():
    """Codex review HIGH-003 (Lot 6, third pass): a client-construction-only
    check cannot catch a revoked/malformed/expired/over-quota key — a real
    call must actually be attempted and its failure surfaced."""
    generator = OpenAIGenerator()
    generator._client = _fake_health_client(should_fail=True)

    results = generator.check_health()

    assert results[0].healthy is False


def test_check_health_validates_the_specific_configured_model():
    """Codex review HIGH-004 (Lot 6, fourth pass): `models.list()`'s result
    was previously discarded — a valid key for *any* model reported healthy
    even if `self.model` itself was misspelled, retired, or inaccessible.
    `models.retrieve()` must be called with exactly the configured model."""
    generator = OpenAIGenerator(model="gpt-4o-custom")
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()

    assert fake.models.retrieve_calls == ["gpt-4o-custom"]


def test_check_health_uses_a_short_bounded_probe_timeout_with_no_retries():
    """Codex review HIGH-002 (Lot 6, fourth pass): the probe previously
    inherited `self.timeout` (30s, sized for a real generation call) and
    the SDK's own default `max_retries=2` (verified live) — a network
    partition could hold a probe for minutes across retries, directly
    contradicting ADR-0010's "single, short, bounded attempt" rule."""
    import modular_rag.generation.synthesizers.openai_gen as module

    generator = OpenAIGenerator(timeout=30.0)
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()

    assert fake.with_options_calls == [
        {"timeout": module._HEALTH_CHECK_TIMEOUT, "max_retries": 0}
    ]
    assert module._HEALTH_CHECK_TIMEOUT < generator.timeout


def test_check_health_reports_busy_when_the_lock_cannot_be_acquired(monkeypatch):
    """Codex review HIGH-002 (Lot 6, fourth pass): `self._health_lock` was
    previously acquired unboundedly (`with self._health_lock:`) — a probe
    stuck despite the timeout/retry fix (e.g. DNS resolution hanging
    outside httpx's own coverage) must not also block every other
    concurrent `/ready` call behind the same lock indefinitely."""
    generator = OpenAIGenerator()
    generator._health_lock.acquire()  # simulate a real probe already in flight
    import modular_rag.generation.synthesizers.openai_gen as module

    monkeypatch.setattr(module, "_HEALTH_LOCK_ACQUIRE_TIMEOUT", 0.05)

    results = generator.check_health()

    assert results[0].healthy is False
    assert results[0].detail == "busy"


def test_check_health_caches_a_healthy_result_so_repeated_calls_dont_reach_the_provider():
    """`/ready` is unauthenticated and exempt from rate limiting — nothing
    else bounds how often the real provider call could be made."""
    generator = OpenAIGenerator()
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()
    generator.check_health()

    assert len(fake.models.retrieve_calls) == 1


def test_check_health_refreshes_once_the_cache_ttl_has_elapsed(monkeypatch):
    import modular_rag.generation.synthesizers.openai_gen as module

    clock = {"now": 0.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])
    generator = OpenAIGenerator()
    fake = _fake_health_client()
    generator._client = fake

    generator.check_health()
    clock["now"] += module._HEALTH_CHECK_CACHE_SECONDS + 1
    generator.check_health()

    assert len(fake.models.retrieve_calls) == 2


def test_check_health_is_unhealthy_with_no_credential_configured(monkeypatch):
    """The real `openai.OpenAI(...)` constructor raises immediately, locally
    (verified live, no network call) when no credential is found anywhere —
    neither the explicit `api_key` nor the `OPENAI_API_KEY` environment
    variable."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = OpenAIGenerator(api_key="")

    results = generator.check_health()

    assert results[0].healthy is False
