from __future__ import annotations

from pydantic import BaseModel

from modular_rag.core.models.retrieved import RetrievedChunk


class RetrievalResult(BaseModel):
    """Return type of `RAGEngine.retrieve()`/`ApplicationService.retrieve()`
    (ADR-0012, Codex review pass 2 HIGH-002): pairs the retrieved chunks with
    a real framework `Trace.id`, the same "trace_id" concept `Answer.trace_id`
    already carries for the `answer()` path. Introduced specifically so
    `/retrieve` can propagate a genuine trace_id, not just `correlation_id`/
    `request_id` — before this, `RAGEngine.retrieve()` returned a bare
    `list[RetrievedChunk]` with no trace of any kind attached.
    """

    chunks: list[RetrievedChunk]
    trace_id: str
