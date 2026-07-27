from __future__ import annotations

from pathlib import Path

from modular_rag.core.models.document import Document


class HTMLParser:
    """Extract text from HTML files using BeautifulSoup. Requires [v1] extras."""

    SUPPORTED_EXTENSIONS = {".html", ".htm"}

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, path: str | Path) -> Document:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ImportError(
                "Install 'beautifulsoup4' (pip install modular-rag[v1]) to parse HTML."
            ) from exc

        p = Path(path)
        raw = p.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()

        metadata: dict[str, str] = {}
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()

        content = soup.get_text(separator="\n", strip=True)
        return Document(
            source=str(p),
            content=content,
            mime_type="text/html",
            metadata=metadata,
        )
