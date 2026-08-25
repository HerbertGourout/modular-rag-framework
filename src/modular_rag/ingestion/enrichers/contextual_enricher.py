from __future__ import annotations

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document


class ContextualEnricher:
    """Prefix each chunk's `embedding_text` with document-level context, so the
    *embedded* representation carries information the raw chunk text alone
    may lack (a short/generic passage embedded on its own can drift from the
    document it belongs to). `Chunk.content` itself is left untouched —
    citations (`generation/citations/builder.py`) and the `/retrieve` API
    both read `content` directly, and showing a synthetic context prefix in
    a user-facing citation would be noise, not signal.

    Deliberately document-context only, not the fuller "document + section +
    metadata context" a hierarchical design might produce: no chunker in this
    codebase currently records the heading/section text a chunk was split
    from (`AdaptiveChunker` splits on heading boundaries but never captures
    what the heading *said*), so section-level context isn't available yet
    without a chunker change — a natural follow-up, not delivered here.

    Not backed by a specific arXiv citation in `docs/research/DIGEST-chunking.md`
    or `DIGEST-retrieval.md` — this codebase's curated research corpus has no
    paper on context-prefixing chunks before embedding (the well-known
    industry technique this approximates, Anthropic's "Contextual Retrieval,"
    generates an LLM-written per-chunk summary; that is deliberately NOT what
    this class does, since an LLM call per chunk at ingest time would
    contradict this codebase's existing lazy/cheap-ingestion posture — see
    `DIGEST-chunking.md`'s own treatment of `2604.04936`/`2602.22225` as
    heavier, V2+-caliber techniques for a similar reason). This is instead a
    free, deterministic prefix using only data already on hand
    (`Document.source`), offered as a cheap default — not a validated,
    literature-backed improvement, and worth A/B-checking against a golden
    set once V1.1's evaluation infrastructure is populated.
    """

    def enrich(self, document: Document, chunks: list[Chunk]) -> list[Chunk]:
        title = document.metadata.get("filename") or document.source
        return [
            chunk.model_copy(
                update={"embedding_text": f"Document: {title}\n\n{chunk.content}"}
            )
            for chunk in chunks
        ]
