from __future__ import annotations

import structlog

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.generation.citations.builder import build_citations
from modular_rag.generation.validators.groundedness import GroundednessValidator

log = structlog.get_logger(__name__)

# Negative-rejection clause per arXiv:2404.10981 §7.1 (Negative Rejection is a
# first-class responsible-generation metric): instructing the model to decline
# when the context lacks the answer is a low-cost hallucination reduction for V1.
_SYSTEM_PROMPT = """\
You are a precise assistant. Answer the user's question using ONLY the provided context.
Cite the source of each claim. If the context is insufficient, say so explicitly.
If the context does not contain the answer, say you don't know — do not guess.
"""


class AnthropicGenerator:
    """Generate grounded answers via the Anthropic Messages API."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        max_tokens: int = 2048,
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self._client: object | None = None
        self._groundedness = GroundednessValidator()

    def name(self) -> str:
        return "anthropic"

    def _get_client(self) -> object:
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic(
                    api_key=self.api_key or None, timeout=self.timeout
                )
            except ImportError as exc:
                raise ImportError("Install 'anthropic' (pip install modular-rag[v1]).") from exc
        return self._client

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        return "\n\n".join(
            f"[{i}] {rc.chunk.metadata.get('source', 'unknown')}\n{rc.chunk.content}"
            for i, rc in enumerate(chunks, 1)
        )

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        import time

        client = self._get_client()
        ctx_text = self._build_context(context)
        t0 = time.perf_counter()
        response = client.messages.create(  # type: ignore[union-attr]
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Context:\n{ctx_text}\n\nQuestion: {query.text}"}
            ],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        trace.add_step(
            TraceStep(
                name="anthropic_generate",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
                metadata={"model": self.model},
            )
        )
        text = response.content[0].text
        answer = Answer(
            query_id=query.id,
            text=text,
            citations=build_citations(context),
            model=self.model,
        )
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)

    def close(self) -> None:
        """Release the underlying anthropic client, if one was ever opened
        (Lot 14, docs/refactoring-plan.md — "own and close clients/
        resources")."""
        if self._client is not None:
            self._client.close()  # type: ignore[attr-defined]
            self._client = None
