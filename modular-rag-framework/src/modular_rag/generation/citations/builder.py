from __future__ import annotations

from modular_rag.core.models.answer import Citation
from modular_rag.core.models.retrieved import RetrievedChunk


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Build Citation objects from a list of RetrievedChunks."""
    return [
        Citation(
            chunk_id=rc.chunk.id,
            source=rc.chunk.metadata.get("source", "unknown"),  # type: ignore[arg-type]
            passage=rc.chunk.content[:300],
            score=rc.score,
            page=rc.chunk.page,
        )
        for rc in chunks
    ]
