from __future__ import annotations

import re

from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.document import Document
from modular_rag.ingestion.chunkers._windowing import (
    TokenCounter,
    iter_sections,
    merge_small_spans,
    resolve_token_counter,
    window_by_tokens,
)

_SECTION_RE = re.compile(r"\n#{1,6}\s+|(?:\n\n){2,}")


class AdaptiveChunker:
    """Split on natural boundaries, then split-then-merge to a token budget.

    Splits on headings/paragraph breaks, caps each oversized section at
    ``chunk_size`` tokens with a sliding window, then runs a merge pass that
    fuses fragments smaller than ``min_chunk_tokens`` into a neighbour. Sizing is
    token-based via a pluggable ``token_counter`` (default: whitespace word
    count, matching ``Chunk.token_estimate``).

    Defaults are 512 tokens / 128-token (25%) overlap per arXiv:2604.12047
    (25% overlap sweet spot). The split-then-merge post-processing and the
    100-token minimum-fragment merge follow arXiv:2603.25333, which reports
    retrieval-completeness gains of +16.5-18.0% from this post-processing.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        max_chunk_size: int | None = None,
        min_chunk_tokens: int = 100,
        token_counter: TokenCounter | str | None = None,
    ) -> None:
        self.chunk_size = max_chunk_size if max_chunk_size is not None else chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_tokens = min_chunk_tokens
        self._count_tokens = resolve_token_counter(token_counter)

    def name(self) -> str:
        return "adaptive"

    def chunk(self, document: Document) -> list[Chunk]:
        """Split on structure, window oversized sections, then merge fragments.

        Sizing is token-based; ``start_char``/``end_char`` stay as true
        character offsets into ``document.content``. The final merge pass fuses
        sub-``min_chunk_tokens`` fragments per arXiv:2603.25333.
        """
        text = document.content
        spans: list[tuple[int, int]] = []
        for start, end in iter_sections(text, _SECTION_RE):
            if self._count_tokens(text[start:end]) <= self.chunk_size:
                spans.append((start, end))
            else:
                spans.extend(
                    window_by_tokens(
                        text, start, end, self.chunk_size, self.chunk_overlap, self._count_tokens
                    )
                )
        spans = merge_small_spans(spans, text, self._count_tokens, self.min_chunk_tokens)
        return [
            Chunk(
                doc_id=document.id,
                content=text[start:end],
                start_char=start,
                end_char=end,
                metadata={"source": document.source},
            )
            for start, end in spans
        ]
