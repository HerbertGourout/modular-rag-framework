from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Encode text strings into dense float vectors."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...

    def name(self) -> str: ...
