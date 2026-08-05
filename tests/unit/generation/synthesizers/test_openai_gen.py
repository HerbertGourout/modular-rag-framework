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
