from __future__ import annotations

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers._windowing import (
    TokenCounter,
    resolve_token_counter,
    window_by_tokens,
)


class FixedSizeChunker:
    """Split content into fixed-size token windows with overlap.

    Sizing is token-based (not character-based): ``chunk_size`` and
    ``chunk_overlap`` count *tokens* via a pluggable ``token_counter``. The
    default counter is a whitespace word count, matching
    ``Chunk.token_estimate``; ``"tiktoken"`` or an encoding name may be passed
    for subword counting (lazy-imported).

    Defaults are 512 tokens / 128-token (25%) overlap per arXiv:2604.12047,
    which reports 25% overlap as the empirical sweet spot (0% overlap worst,
    50% no better while doubling index size).
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        token_counter: TokenCounter | str | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._count_tokens = resolve_token_counter(token_counter)

    def name(self) -> str:
        return "fixed-size"

    def chunk(self, document: Document) -> list[Chunk]:
        """Return token-bounded chunks with character-accurate offsets.

        Windows are measured in tokens (defaults per arXiv:2604.12047) while
        ``start_char``/``end_char`` remain true character offsets into
        ``document.content``.
        """
        text = document.content
        spans = window_by_tokens(
            text, 0, len(text), self.chunk_size, self.chunk_overlap, self._count_tokens
        )
        return [
            Chunk(
                doc_id=document.id,
                content=text[start:end],
                start_char=start,
                end_char=end,
                tenant_id=document.tenant_id,
                classification=document.classification,
                metadata={"source": document.source},
            )
            for start, end in spans
        ]
