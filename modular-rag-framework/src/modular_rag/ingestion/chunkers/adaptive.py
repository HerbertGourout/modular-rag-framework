from __future__ import annotations

import re

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document

_SECTION_RE = re.compile(r"\n#{1,6}\s+|(?:\n\n){2,}")


class AdaptiveChunker:
    """Split on natural boundaries (headings, paragraphs) then enforce a max size."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64, max_chunk_size: int | None = None) -> None:
        self.chunk_size = max_chunk_size if max_chunk_size is not None else chunk_size
        self.chunk_overlap = chunk_overlap

    def name(self) -> str:
        return "adaptive"

    def chunk(self, document: Document) -> list[Chunk]:
        sections = _SECTION_RE.split(document.content)
        chunks: list[Chunk] = []
        cursor = 0
        for section in sections:
            section = section.strip()
            if not section:
                cursor += len(section) + 1
                continue
            if len(section) <= self.chunk_size:
                chunks.append(
                    Chunk(
                        doc_id=document.id,
                        content=section,
                        start_char=cursor,
                        end_char=cursor + len(section),
                        metadata={"source": document.source},
                    )
                )
            else:
                stride = self.chunk_size - self.chunk_overlap
                start = 0
                while start < len(section):
                    end = min(start + self.chunk_size, len(section))
                    chunks.append(
                        Chunk(
                            doc_id=document.id,
                            content=section[start:end],
                            start_char=cursor + start,
                            end_char=cursor + end,
                            metadata={"source": document.source},
                        )
                    )
                    if end == len(section):
                        break
                    start += stride
            cursor += len(section) + 1
        return chunks
