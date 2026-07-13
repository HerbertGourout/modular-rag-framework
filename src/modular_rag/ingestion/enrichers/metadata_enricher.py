from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from modular_rag.core.models.document import Document


class MetadataEnricher:
    """Add filesystem-derived metadata to a Document."""

    def enrich(self, document: Document) -> Document:
        p = Path(document.source)
        extra: dict[str, object] = {
            "filename": p.name,
            "extension": p.suffix.lower(),
            "enriched_at": datetime.now(UTC).isoformat(),
        }
        if p.exists():
            extra["size_bytes"] = p.stat().st_size
        merged = {**document.metadata, **extra}
        return document.model_copy(update={"metadata": merged})
