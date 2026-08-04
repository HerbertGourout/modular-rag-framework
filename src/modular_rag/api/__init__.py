from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from modular_rag.app.bootstrap import load_pipeline
from modular_rag.core.models.answer import Answer


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    text: str
    citations: list[dict]
    trace_id: str | None = None


def create_app(manifest_path: str) -> FastAPI:
    """Factory: load a pipeline from a manifest and expose it as a FastAPI app.

    `QuestionRequest`/`AnswerResponse` are module-level, not nested inside this
    function, on purpose (Lot 8, docs/refactoring-plan.md): with
    `from __future__ import annotations`, a locally-scoped class produces an
    unresolvable forward-reference annotation that FastAPI silently
    misinterprets as a query parameter instead of a request body — this is
    what made `POST /answer` return 422 on every documented call before this
    fix. See tests/unit/api/test_api.py for the regression test.
    """
    pipeline = load_pipeline(manifest_path)

    api = FastAPI(
        title="Modular RAG API",
        version="0.0.1",
        description="Production-grade RAG and agentic reasoning API.",
    )

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "pipeline": pipeline.manifest_id}

    @api.post("/answer", response_model=AnswerResponse)
    def answer(req: QuestionRequest) -> AnswerResponse:
        try:
            ans: Answer = pipeline.answer(req.question)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return AnswerResponse(
            text=ans.text,
            citations=[c.model_dump() for c in ans.citations],
            trace_id=ans.trace_id,
        )

    @api.get("/retrieve")
    def retrieve(q: str, k: int = 10) -> list[dict]:
        chunks = pipeline.retrieve(q, k=k)
        return [
            {"chunk_id": rc.chunk.id, "score": rc.score, "content": rc.chunk.content[:300]}
            for rc in chunks
        ]

    return api
