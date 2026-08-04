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


def test_index_replaces_rather_than_appends_to_the_previous_corpus() -> None:
    """A second index() call fully replaces `_chunks` — there is no
    incremental add. Chunks from the first call are gone unless re-included."""
    retriever = BM25Retriever()
    first = _chunk("first batch content about cats")
    retriever.index([first])

    second = _chunk("second batch content about dogs")
    retriever.index([second])

    result = retriever.retrieve(Query(text="cats"), k=10)
    assert result == []  # `first` is no longer in the corpus at all


def test_bm25_retriever_has_no_delete_method() -> None:
    """Structural gap behind docs/refactoring-plan.md §2's 'Data deletion/
    update' row: BM25Retriever implements `index()` but not `Indexer.delete()`
    or `.clear()`. There is no way to remove a single chunk from the lexical
    index short of re-calling `index()` with the full remaining corpus.
    """
    retriever = BM25Retriever()

    assert not hasattr(retriever, "delete")
    assert not hasattr(retriever, "clear")


@pytest.mark.asyncio
async def test_aretrieve_delegates_to_retrieve() -> None:
    retriever = BM25Retriever()
    corpus = _diverse_corpus()
    retriever.index(corpus)

    result = await retriever.aretrieve(Query(text="retrieval augmented generation"), k=5)

    assert result and result[0].chunk.id == corpus[0].id
