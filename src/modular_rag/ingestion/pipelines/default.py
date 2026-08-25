from __future__ import annotations

from pathlib import Path

import structlog

from modular_rag.contracts.chunking import Chunker
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.ingestion.enrichers.contextual_enricher import ContextualEnricher
from modular_rag.ingestion.enrichers.metadata_enricher import MetadataEnricher
from modular_rag.ingestion.normalizers.text_normalizer import TextNormalizer
from modular_rag.ingestion.parsers.docx_parser import DocxParser
from modular_rag.ingestion.parsers.html_parser import HTMLParser
from modular_rag.ingestion.parsers.pdf_parser import PDFParser
from modular_rag.ingestion.parsers.text_parser import TextParser

log = structlog.get_logger(__name__)

_PARSERS = [TextParser(), PDFParser(), DocxParser(), HTMLParser()]
_NORMALIZER = TextNormalizer()
_ENRICHER = MetadataEnricher()
_CONTEXTUAL_ENRICHER = ContextualEnricher()


def _apply_tenant_id(document: Document, tenant_id: str | None) -> Document:
    """Tenant-aware ingestion: an explicit `tenant_id` always wins over
    whatever the document already carries — never silently overridden by
    anything a parser/enricher might set from source metadata in the future
    (no parser sets `Document.tenant_id` today; this guarantee is
    deliberately defensive, not a fix for a current leak). `None` (no
    `--tenant-id` supplied) leaves the document unchanged, preserving prior
    behavior for unsecured/local manifests exactly."""
    if tenant_id is None:
        return document
    return document.model_copy(update={"tenant_id": tenant_id})


def ingest_path(path: str | Path, chunker: Chunker, tenant_id: str | None = None) -> list[Chunk]:
    """Parse, normalise, enrich, chunk, and contextually re-enrich a single file.

    `tenant_id` (tenant-aware ingestion, follow-up to the tenant fail-closed
    fix on `ask`): applied to the `Document` right before chunking, after
    normalization/enrichment, so it's the last word on the document's
    identity going into `chunker.chunk()`. Every built-in `Chunker`
    (`ingestion/chunkers/fixed.py`, `adaptive.py`) already copies
    `document.tenant_id` onto each produced `Chunk` — this is the only piece
    that was missing: nothing set it on the `Document` in the first place.

    `ContextualEnricher` runs last, after chunking (unlike `MetadataEnricher`,
    which runs on the `Document` before chunking): it needs the produced
    `Chunk`s to set each one's `embedding_text`, which `RAGEngine.ingest_chunks()`
    embeds instead of `content` when set — see that class's own docstring.
    """
    p = Path(path)
    parser = next((pr for pr in _PARSERS if pr.supports(p)), None)
    if parser is None:
        log.warning("ingestion.unsupported", path=str(p))
        return []
    doc = parser.parse(p)
    doc = _NORMALIZER.normalize(doc)
    doc = _ENRICHER.enrich(doc)
    doc = _apply_tenant_id(doc, tenant_id)
    chunks = chunker.chunk(doc)
    chunks = _CONTEXTUAL_ENRICHER.enrich(doc, chunks)
    log.debug("ingestion.chunked", path=str(p), chunks=len(chunks))
    return chunks


def ingest_directory(
    directory: str | Path, chunker: Chunker, tenant_id: str | None = None
) -> list[Chunk]:
    """Recursively ingest all supported files in a directory, all under the
    same `tenant_id` — one CLI/API call ingests one tenant's batch."""
    all_chunks: list[Chunk] = []
    for p in Path(directory).rglob("*"):
        if p.is_file():
            all_chunks.extend(ingest_path(p, chunker, tenant_id=tenant_id))
    log.info("ingestion.directory_done", dir=str(directory), total_chunks=len(all_chunks))
    return all_chunks
