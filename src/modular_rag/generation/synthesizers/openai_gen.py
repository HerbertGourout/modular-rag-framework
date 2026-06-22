from __future__ import annotations

import structlog

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.generation.citations.builder import build_citations

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a precise assistant. Answer the user's question using ONLY the provided context.
Cite the source of each claim. If the context is insufficient, say so explicitly.
"""


class OpenAIGenerator:
    """Generate grounded answers via the OpenAI Chat API."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_key: str = "",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self._client: object | None = None

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
            parts.append(f"[{i}] Source: {rc.chunk.metadata.get('source', 'unknown')}\n{rc.chunk.content}")
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
        return Answer(query_id=query.id, text=text, citations=citations, model=self.model)

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)
