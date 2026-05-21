from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document


@runtime_checkable
class Chunker(Protocol):
    """Split a Document into a list of Chunks."""

    def chunk(self, document: Document) -> list[Chunk]: ...

    def name(self) -> str: ...
