"""Unit tests for the citation builder."""
from __future__ import annotations

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.ids import new_id
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.generation.citations.builder import build_citations


def _retrieved(
    content: str,
    metadata: dict | None = None,
    score: float = 0.8,
    page: int | None = None,
) -> RetrievedChunk:
    chunk = Chunk(doc_id=new_id(), content=content, metadata=metadata or {}, page=page)
    return RetrievedChunk(
        chunk=chunk, score=score, rank=1, retrieval_method=RetrievalMethod.HYBRID
    )


def test_empty_context_yields_no_citations():
    assert build_citations([]) == []


def test_citation_fields_come_from_chunk():
    rc = _retrieved("some passage", metadata={"source": "report.pdf"}, score=0.42, page=7)

    [citation] = build_citations([rc])

    assert citation.chunk_id == rc.chunk.id
    assert citation.source == "report.pdf"
    assert citation.passage == "some passage"
    assert citation.score == 0.42
    assert citation.page == 7


def test_missing_source_falls_back_to_unknown():
    [citation] = build_citations([_retrieved("passage")])
    assert citation.source == "unknown"


def test_passage_truncates_at_last_sentence_boundary_within_limit():
    # arXiv:2506.10408 §4.1 — avoid severing the sentence that supports a claim.
    sentence = "This sentence has several words in it. "  # 39 chars
    content = sentence * 15  # 585 chars, boundaries every 39 chars
    [citation] = build_citations([_retrieved(content)])

    assert citation.passage.endswith(".")
    assert content.startswith(citation.passage)
    assert len(citation.passage) <= 300
    # Last "." within the 300-char window ends at 39 * 6 + 38 = 272.
    assert len(citation.passage) == 272


def test_passage_hard_cut_at_300_when_no_sentence_boundary():
    # No sentence-ending punctuation in range → fall back to a hard cut.
    [citation] = build_citations([_retrieved("x" * 1000)])
    assert len(citation.passage) == 300


def test_short_content_is_returned_unchanged():
    content = "A short grounded passage."
    [citation] = build_citations([_retrieved(content)])
    assert citation.passage == content


def test_one_citation_per_chunk_in_order():
    rcs = [_retrieved(f"passage {i}") for i in range(3)]
    citations = build_citations(rcs)
    assert [c.chunk_id for c in citations] == [rc.chunk.id for rc in rcs]
