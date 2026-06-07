from __future__ import annotations

from pathlib import Path

from modular_rag.core.models.document import Document


class TextParser:
    """Parse plain-text and Markdown files into a Document."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".rst"}

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, path: str | Path) -> Document:
        p = Path(path)
        return Document(
            source=str(p),
            content=p.read_text(encoding="utf-8", errors="replace"),
            mime_type="text/plain",
        )
