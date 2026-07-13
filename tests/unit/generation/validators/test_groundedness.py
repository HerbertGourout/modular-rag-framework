"""Unit tests for GroundednessValidator (token-overlap heuristic)."""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.generation.validators.groundedness import GroundednessValidator


def _context(*contents: str) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk=Chunk(doc_id=new_id(), content=c),
            score=0.9,
            rank=i,
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for i, c in enumerate(contents, 1)
    ]


def _answer(text: str) -> Answer:
    return Answer(query_id=new_id(), text=text, model="test")


def test_empty_context_scores_zero():
    validator = GroundednessValidator()
    assert validator.validate(_answer("any answer"), []) == 0.0


def test_empty_answer_scores_zero():
    validator = GroundednessValidator()
    assert validator.validate(_answer(""), _context("some context")) == 0.0


def test_fully_grounded_answer_scores_one():
    validator = GroundednessValidator()
    score = validator.validate(
        _answer("hybrid retrieval fuses scores"),
        _context("Hybrid retrieval fuses vector and lexical scores via RRF."),
    )
    assert score == 1.0


def test_ungrounded_answer_scores_zero():
    validator = GroundednessValidator()
    score = validator.validate(
        _answer("bananas oranges kiwis"),
        _context("Hybrid retrieval fuses vector and lexical scores."),
    )
    assert score == 0.0


def test_partial_overlap_is_ratio_of_answer_tokens():
    validator = GroundednessValidator()
    # 2 of 4 answer tokens ("hybrid", "retrieval") appear in the context.
    score = validator.validate(
        _answer("hybrid retrieval bananas kiwis"),
        _context("hybrid retrieval works well"),
    )
    assert score == 0.5


def test_matching_is_case_insensitive():
    validator = GroundednessValidator()
    score = validator.validate(_answer("HYBRID RETRIEVAL"), _context("hybrid retrieval"))
    assert score == 1.0


def test_overlap_counts_across_multiple_chunks():
    validator = GroundednessValidator()
    score = validator.validate(
        _answer("vector lexical"),
        _context("vector search", "lexical search"),
    )
    assert score == 1.0
