from __future__ import annotations

import re

from modular_rag.core.models.answer import Citation
from modular_rag.core.models.retrieved import RetrievedChunk

_PASSAGE_LIMIT = 300
_SENTENCE_END = re.compile(r"[.!?]")


def _truncate_passage(content: str, limit: int = _PASSAGE_LIMIT) -> str:
    """Truncate ``content`` at the last sentence boundary within ``limit`` chars.

    Blunt fixed-length truncation (``content[:limit]``) can sever the very
    sentence that supports a cited claim; arXiv:2506.10408 §4.1 favours
    distill/refine over naive concatenation/truncation of retrieved passages.
    As a lightweight V1 approximation we cut at the last sentence-ending
    punctuation (``.``/``!``/``?``) that falls within ``limit`` characters, and
    fall back to a hard cut at ``limit`` when no boundary is found. A non-empty
    ``content`` always yields a non-empty passage.
    """
    if len(content) <= limit:
        return content
    window = content[:limit]
    last_boundary = -1
    for match in _SENTENCE_END.finditer(window):
        last_boundary = match.end()  # index just past the punctuation
    if last_boundary > 0:
        return content[:last_boundary]
    return window  # no sentence boundary in range → hard cut


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Build Citation objects from a list of RetrievedChunks."""
    return [
        Citation(
            chunk_id=rc.chunk.id,
            source=rc.chunk.metadata.get("source", "unknown"),  # type: ignore[arg-type]
            passage=_truncate_passage(rc.chunk.content),
            score=rc.score,
            page=rc.chunk.page,
        )
        for rc in chunks
    ]
