from __future__ import annotations

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document


class FixedSizeChunker:
    """Split document content into fixed-size windows with optional overlap."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def name(self) -> str:
        return "fixed"

    def chunk(self, document: Document) -> list[Chunk]:
        text = document.content
        stride = self.chunk_size - self.chunk_overlap
        chunks: list[Chunk] = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(
                Chunk(
                    doc_id=document.id,
                    content=text[start:end],
                    start_char=start,
                    end_char=end,
                    metadata={"source": document.source},
                )
            )
            if end == len(text):
                break
            start += stride
        return chunks
