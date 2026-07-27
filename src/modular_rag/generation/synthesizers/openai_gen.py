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


class OpenAIGenerator:
    """Generate grounded answers via the OpenAI Chat API."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        # Low-variance engineering default, unsourced by the research corpus
        # (docs/research/DIGEST-generation.md #7) — sweep during V1.1 evaluation.
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_key: str = "",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self._client: object | None = None
        self._groundedness = GroundednessValidator()

    def name(self) -> str:
        return "openai"

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key or None)
            except ImportError as exc:
                raise ImportError("Install 'openai' (pip install modular-rag[v1]).") from exc
        return self._client

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        parts = []
        for i, rc in enumerate(chunks, 1):
            source = rc.chunk.metadata.get("source", "unknown")
            parts.append(f"[{i}] Source: {source}\n{rc.chunk.content}")
        return "\n\n".join(parts)

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        import time

        client = self._get_client()
        ctx_text = self._build_context(context)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{ctx_text}\n\nQuestion: {query.text}"},
        ]
        t0 = time.perf_counter()
        response = client.chat.completions.create(  # type: ignore[union-attr]
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        usage = response.usage
        trace.add_step(
            TraceStep(
                name="openai_generate",
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                metadata={"model": self.model},
            )
        )
        text = response.choices[0].message.content or ""
        citations = build_citations(context)
        log.debug("openai.generated", tokens=usage.total_tokens, ms=latency_ms)
        answer = Answer(query_id=query.id, text=text, citations=citations, model=self.model)
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)
