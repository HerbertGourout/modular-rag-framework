"""Characterization tests for retrieval/retrievers/bm25.py.

Lot 4 (docs/refactoring-plan.md), Part 2. `BM25Retriever` had zero direct
unit tests before this — only indirect coverage via test_hybrid.py's fakes.
"""
from __future__ import annotations

import pytest

from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever


def _chunk(content: str) -> Chunk:
    return Chunk(doc_id=new_id(), content=content)


def test_retrieve_before_any_index_call_returns_empty_list() -> None:
    retriever = BM25Retriever()

    result = retriever.retrieve(Query(text="anything"))

    assert result == []


def _diverse_corpus() -> list[Chunk]:
    """5+ varied documents — large/diverse enough that BM25's IDF term stays
    positive for a genuinely rare, matching term (see the dedicated
    small-corpus test below for what happens when it isn't)."""
    return [
        _chunk("retrieval augmented generation combines search and language models"),
        _chunk("the weather today is sunny with a light breeze"),
        _chunk("python is a popular programming language for data science"),
        _chunk("the stock market fell sharply amid recession fears"),
        _chunk("cooking pasta requires boiling water and salt"),
    ]


def test_retrieve_ranks_by_term_overlap() -> None:
    retriever = BM25Retriever()
    corpus = _diverse_corpus()
    retriever.index(corpus)

    result = retriever.retrieve(Query(text="retrieval augmented generation"), k=10)

    assert result[0].chunk.id == corpus[0].id


def test_retrieve_returns_no_hits_for_a_relevant_document_in_a_too_small_corpus() -> None:
    """**Newly discovered, not in docs/refactoring-plan.md §2.** `rank_bm25`'s
    IDF term can be zero or *negative* when a query term appears in most or
    all documents of a small corpus — trivially likely with only 1-2 chunks
    indexed (e.g. `examples/simple_qa/`'s small demo corpus, or any small
    real deployment). `BM25Retriever.retrieve()` then filters those
    non-positive scores out via `if score > 0`, so a document that is
    genuinely the best (or only) match for the query silently returns zero
    hits. Confirmed directly against rank_bm25: a 2-document corpus where the
    query terms appear in only one doc still scores that doc `0.0`; a
    1-document corpus scores its only doc *negative* (`-0.82`) for its own
    content. Not fixed here — a candidate for Lot 12b (index/retrieval
    correctness) or an upstream rank_bm25 IDF-floor workaround.
    """
    retriever = BM25Retriever()
    only_relevant_chunk = _chunk("retrieval augmented generation is a hybrid technique")
    retriever.index([only_relevant_chunk])

    result = retriever.retrieve(Query(text="retrieval augmented generation"), k=10)

    assert result == []  # the only document, despite being an exact topical match


def test_retrieve_excludes_zero_score_chunks() -> None:
    """Only chunks with score > 0 are returned — a query with no term overlap
    at all against a chunk yields no hit for it, not a zero-score hit."""
    retriever = BM25Retriever()
    only_chunk = _chunk("apples and oranges")
    retriever.index([only_chunk])

    result = retriever.retrieve(Query(text="completely different unrelated words"), k=10)

    assert result == []


def test_index_appends_to_the_previous_corpus() -> None:
    """Fixed in Lot 12a (docs/refactoring-plan.md): a second `index()` call
    used to fully replace `_chunks`, silently dropping the first batch. It
    now appends and rebuilds — both batches stay searchable. Uses a diverse
    base corpus (not a bare 2-document one) to stay clear of the separate
    small-corpus IDF-floor gap characterized above."""
    retriever = BM25Retriever()
    first_batch = _diverse_corpus()
    retriever.index(first_batch)

    second = _chunk("a brand new document about volcanic eruptions and lava flow")
    retriever.index([second])

    original = retriever.retrieve(Query(text="retrieval augmented generation"), k=10)
    added = retriever.retrieve(Query(text="volcanic eruptions lava"), k=10)
    assert original and original[0].chunk.id == first_batch[0].id
    assert added and added[0].chunk.id == second.id


def test_delete_removes_only_the_matching_chunk() -> None:
    """Closes the structural gap behind docs/refactoring-plan.md §2's 'Data
    deletion/update' row (Lot 12a)."""
    retriever = BM25Retriever()
    corpus = _diverse_corpus()
    retriever.index(corpus)
    to_remove = corpus[0]  # the "retrieval augmented generation" doc

    retriever.delete([to_remove.id])

    removed_topic = retriever.retrieve(Query(text="retrieval augmented generation"), k=10)
    still_present = retriever.retrieve(Query(text="python programming language"), k=10)
    assert removed_topic == []
    assert still_present and still_present[0].chunk.id == corpus[2].id


def test_delete_on_empty_corpus_does_not_raise() -> None:
    BM25Retriever().delete(["nonexistent-id"])  # must not raise


def test_clear_empties_the_corpus() -> None:
    retriever = BM25Retriever()
    retriever.index(_diverse_corpus())

    retriever.clear()

    assert retriever.retrieve(Query(text="retrieval augmented generation"), k=10) == []


@pytest.mark.asyncio
async def test_aretrieve_delegates_to_retrieve() -> None:
    retriever = BM25Retriever()
    corpus = _diverse_corpus()
    retriever.index(corpus)

    result = await retriever.aretrieve(Query(text="retrieval augmented generation"), k=5)

    assert result and result[0].chunk.id == corpus[0].id
