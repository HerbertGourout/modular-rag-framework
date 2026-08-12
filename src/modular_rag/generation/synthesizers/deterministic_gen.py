"""Deterministic, dependency-free generation adapter — no LLM API call, no
network. Registered as `generator.type: "deterministic"` (Lot 4, secure
preset e2e correction) so a real e2e pipeline can wire a contract-conformant
`Generator` with no external LLM key, alongside
`adapters.embeddings.deterministic_embedder.DeterministicEmbedder`.
"""
from __future__ import annotations

import time

from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.answer import Answer, Citation
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.generation.citations.builder import build_citations
from modular_rag.generation.validators.groundedness import GroundednessValidator


class DeterministicGenerator:
    """Extractive, template-based `Generator`: quotes the top-ranked
    retrieved chunk(s) verbatim instead of calling an LLM. Deterministic —
    identical `(query, context)` always produces the identical answer text,
    on any machine, forever — and needs no API key, network access, or model
    download.

    Quoting real context content directly (rather than paraphrasing) is what
    keeps `GroundednessValidator`'s lexical-overlap gate from ever refusing:
    the answer text and the cited content share almost all of their tokens by
    construction. The answer text is built directly from each citation's own
    `passage` field (`build_citations()` is called *first*, then quoted) —
    not from a second, independently-truncated slice of `chunk.content` — so
    the quoted span can never disagree with what its own citation covers
    (Codex review: an earlier version hard-sliced `chunk.content[:300]`
    separately from `build_citations()`'s sentence-boundary-aware truncation,
    so a chunk with a sentence boundary before char 300 could get a shorter
    citation `passage` than the text actually quoted in the answer — the
    exact citation-integrity property this generator and the e2e lot around
    it are meant to prove).
    """

    def __init__(self, max_chunks: int = 3) -> None:
        # Codex review: `max_chunks` reaches here from manifest config
        # (`generator.config.max_chunks`) unvalidated. `citations[:max_chunks]` with
        # max_chunks<=0 quotes zero (or, for a negative value, a confusing tail slice
        # of) passages in `_build_text()`'s answer text, while `generate()` still
        # attaches the *full*, untruncated citation list to the returned `Answer` —
        # exactly the text-says-nothing-but-citations-claim-something integrity gap
        # this generator exists to prove doesn't happen. Same fail-fast-at-construction
        # pattern as DeterministicEmbedder's `dimensions` validation.
        if max_chunks < 1:
            raise ConfigurationError(
                f"DeterministicGenerator max_chunks must be a positive integer, got {max_chunks}."
            )
        self.max_chunks = max_chunks
        self._groundedness = GroundednessValidator()

    def name(self) -> str:
        return "deterministic"

    def _build_text(self, query: Query, citations: list[Citation]) -> str:
        if not citations:
            return "I don't know based on the provided context."
        parts = [f"Regarding '{query.text}', the retrieved context states:"]
        for citation in citations[: self.max_chunks]:
            parts.append(f"- ({citation.source}) {citation.passage}")
        return "\n".join(parts)

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        t0 = time.perf_counter()
        citations = build_citations(context)
        text = self._build_text(query, citations)
        latency_ms = (time.perf_counter() - t0) * 1000
        trace.add_step(
            TraceStep(
                name="deterministic_generate",
                latency_ms=latency_ms,
                metadata={"context_chunks": len(context)},
            )
        )
        answer = Answer(query_id=query.id, text=text, citations=citations, model="deterministic")
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)
