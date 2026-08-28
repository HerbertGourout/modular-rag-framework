"""Unit tests for generation/synthesizers/deterministic_gen.py.

Mirrors the structure of tests/unit/generation/synthesizers/test_openai_gen.py's
`_context()` helper — no fake client needed here since DeterministicGenerator
never calls out to anything.
"""
from __future__ import annotations

import asyncio

import pytest

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace
from modular_rag.generation.synthesizers.deterministic_gen import DeterministicGenerator


def _context(contents: list[str]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk=Chunk(
                doc_id=new_id(), content=c, metadata={"source": f"doc{i}.txt"}, tenant_id="t1"
            ),
            score=0.9,
            rank=i,
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for i, c in enumerate(contents, 1)
    ]


def _generate(generator: DeterministicGenerator, contents: list[str], question: str = "What?"):
    query = Query(text=question, tenant_id="t1")
    trace = Trace(query_id=query.id)
    answer = generator.generate(query, _context(contents), trace)
    return query, trace, answer


def test_answer_quotes_context_content():
    _, _, answer = _generate(DeterministicGenerator(), ["Blue whales are the largest animals."])

    assert "Blue whales are the largest animals." in answer.text


def test_answer_carries_model_name_and_query_id():
    query, _, answer = _generate(DeterministicGenerator(), ["some context"])

    assert answer.model == "deterministic"
    assert answer.query_id == query.id


def test_one_citation_per_context_chunk():
    _, _, answer = _generate(DeterministicGenerator(), ["chunk one text", "chunk two text"])

    assert len(answer.citations) == 2
    assert [c.source for c in answer.citations] == ["doc1.txt", "doc2.txt"]


@pytest.mark.parametrize("max_chunks", [0, -1, -3])
def test_non_positive_max_chunks_is_rejected_at_construction(max_chunks):
    """Codex review: previously wired/validated successfully, then quoted zero (or a
    confusing tail slice of) passages in the answer text while still attaching the
    *full* citation list — the exact text-says-nothing-but-citations-claim-something
    integrity gap this generator exists to prove doesn't happen."""
    with pytest.raises(ConfigurationError, match=str(max_chunks)):
        DeterministicGenerator(max_chunks=max_chunks)


def test_max_chunks_limits_how_many_are_quoted_but_not_cited():
    """Citations cover every retrieved chunk (build_citations(context) — the
    same helper every other generator uses); only the *quoted text* in the
    answer body is capped by max_chunks."""
    generator = DeterministicGenerator(max_chunks=1)

    _, _, answer = _generate(generator, ["first chunk content", "second chunk content"])

    assert len(answer.citations) == 2
    assert "first chunk content" in answer.text
    assert "second chunk content" not in answer.text


def test_quoted_span_never_exceeds_its_own_citation_passage():
    """Codex review: regression for a bug where the answer text was built
    from an independent `chunk.content[:300]` hard slice while the citation
    passage came from `build_citations()`'s sentence-boundary-aware
    truncation — for a chunk over 300 chars with a sentence boundary before
    that limit, the citation `passage` was shorter than what the answer text
    actually quoted, so the citation didn't fully cover its own quote."""
    long_content = (
        "Blue whales are the largest animals ever known to have lived on Earth. "
        + ("Additional detail padding this passage well past the passage limit. " * 5)
    )
    assert len(long_content) > 300
    assert "." in long_content[:300]  # a sentence boundary exists before the limit

    _, _, answer = _generate(DeterministicGenerator(), [long_content])

    passage = answer.citations[0].passage
    assert passage in answer.text
    # The quoted line for this citation must not contain characters beyond
    # what the citation's own (shorter, sentence-truncated) passage covers.
    quoted_line = next(line for line in answer.text.splitlines() if passage in line)
    assert quoted_line.endswith(passage)


def test_empty_context_produces_a_refusal_with_no_citations():
    _, _, answer = _generate(DeterministicGenerator(), [])

    assert answer.text == "I don't know based on the provided context."
    assert answer.citations == []


def test_trace_step_is_emitted():
    _, trace, _ = _generate(DeterministicGenerator(), ["some context"])

    steps = [s for s in trace.steps if s.name == "deterministic_generate"]
    assert len(steps) == 1
    assert steps[0].metadata["context_chunks"] == 1
    assert steps[0].latency_ms >= 0


def test_generate_is_deterministic_across_separate_instances():
    """The property the e2e restart scenario depends on. Reuses the same
    RetrievedChunk objects for both calls — `_context()` itself assigns a
    fresh random chunk id per call (`Chunk.id` defaults to `new_id()`), so
    calling it twice would make the *fixture* the source of any difference,
    not the generator under test."""
    query = Query(text="What about whales?", tenant_id="t1")
    context = _context(["The retrieved passage about whales."])

    answer_a = DeterministicGenerator().generate(query, context, Trace(query_id=query.id))
    answer_b = DeterministicGenerator().generate(query, context, Trace(query_id=query.id))

    assert answer_a.text == answer_b.text
    assert [c.chunk_id for c in answer_a.citations] == [c.chunk_id for c in answer_b.citations]


def test_agenerate_matches_generate():
    generator = DeterministicGenerator()
    context = _context(["shared context"])
    query = Query(text="q", tenant_id="t1")

    sync_answer = generator.generate(query, context, Trace(query_id=query.id))
    async_answer = asyncio.run(generator.agenerate(query, context, Trace(query_id=query.id)))

    assert sync_answer.text == async_answer.text


def test_name_is_stable_identifier():
    assert DeterministicGenerator().name() == "deterministic"


def test_answer_records_a_real_measured_zero_cost():
    """Codex review (pass 1, HIGH-003): this generator never calls an LLM,
    so cost_usd=0.0 is a real, confident measurement -- recorded explicitly
    so a benchmark reading Answer.metadata.get("cost_usd") sees a genuine
    measurement, not an indistinguishable-from-unmeasured None."""
    _, _, answer = _generate(DeterministicGenerator(), ["some context"])

    assert answer.metadata.get("cost_usd") == 0.0


def test_refusal_answer_still_records_the_measured_zero_cost():
    """The refusal path rebuilds the Answer via model_copy(update={...}) --
    confirm metadata (set before the refusal check) survives that copy."""
    _, _, answer = _generate(DeterministicGenerator(), [])

    assert answer.text == "I don't know based on the provided context."
    assert answer.metadata.get("cost_usd") == 0.0
