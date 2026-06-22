from __future__ import annotations

from pathlib import Path

import structlog

from modular_rag.contracts.chunking import Chunker
from modular_rag.core.models.chunk import Chunk
from modular_rag.ingestion.enrichers.metadata_enricher import MetadataEnricher
from modular_rag.ingestion.normalizers.text_normalizer import TextNormalizer
from modular_rag.ingestion.parsers.pdf_parser import PDFParser
from modular_rag.ingestion.parsers.text_parser import TextParser

log = structlog.get_logger(__name__)

_PARSERS = [TextParser(), PDFParser()]
_NORMALIZER = TextNormalizer()
_ENRICHER = MetadataEnricher()


def ingest_path(path: str | Path, chunker: Chunker) -> list[Chunk]:
    """Parse, normalise, enrich, and chunk a single file."""
    p = Path(path)
    parser = next((pr for pr in _PARSERS if pr.supports(p)), None)
    if parser is None:
        log.warning("ingestion.unsupported", path=str(p))
        return []
    doc = parser.parse(p)
    doc = _NORMALIZER.normalize(doc)
    doc = _ENRICHER.enrich(doc)
    chunks = chunker.chunk(doc)
    log.debug("ingestion.chunked", path=str(p), chunks=len(chunks))
    return chunks


def ingest_directory(directory: str | Path, chunker: Chunker) -> list[Chunk]:
    """Recursively ingest all supported files in a directory."""
    all_chunks: list[Chunk] = []
    for p in Path(directory).rglob("*"):
        if p.is_file():
            all_chunks.extend(ingest_path(p, chunker))
    log.info("ingestion.directory_done", dir=str(directory), total_chunks=len(all_chunks))
    return all_chunks
