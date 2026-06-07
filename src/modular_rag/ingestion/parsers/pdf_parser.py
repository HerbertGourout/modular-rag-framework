from __future__ import annotations

from pathlib import Path

from modular_rag.core.models.document import Document


class PDFParser:
    """Extract text from PDF files using pymupdf (fitz). Requires [v1] extras."""

    SUPPORTED_EXTENSIONS = {".pdf"}

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, path: str | Path) -> Document:
        try:
            import fitz  # pymupdf
        except ImportError as exc:
            raise ImportError("Install 'pymupdf' (pip install modular-rag[v1]) to parse PDFs.") from exc

        p = Path(path)
        doc = fitz.open(str(p))
        pages = [page.get_text() for page in doc]
        content = "\n\n".join(pages)
        doc.close()
        return Document(
            source=str(p),
            content=content,
            mime_type="application/pdf",
            metadata={"page_count": len(pages)},
        )
