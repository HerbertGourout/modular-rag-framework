from __future__ import annotations

import re
import unicodedata

from modular_rag.core.models.document import Document


class TextNormalizer:
    """Normalize whitespace and unicode in Document content."""

    @staticmethod
    def normalize(document: Document) -> Document:
        text = document.content
        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        return document.model_copy(update={"content": text})
