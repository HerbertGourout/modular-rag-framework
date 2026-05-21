from __future__ import annotations

from typing import Protocol, runtime_checkable

from modular_rag.core.models.chunk import Chunk


@runtime_checkable
class Indexer(Protocol):
    """Write and delete Chunks in a persistent store (vector or lexical)."""

    def index(self, chunks: list[Chunk]) -> None: ...

    def delete(self, ids: list[str]) -> None: ...

    def clear(self) -> None: ...

    def name(self) -> str: ...
