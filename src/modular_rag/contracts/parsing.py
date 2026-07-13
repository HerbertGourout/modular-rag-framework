from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from modular_rag.core.models.document import Document


@runtime_checkable
class Parser(Protocol):
    """Parse a source file into a Document."""

    def supports(self, path: str | Path) -> bool: ...

    def parse(self, path: str | Path) -> Document: ...
