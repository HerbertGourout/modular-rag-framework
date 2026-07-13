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
