"""Tests for api/__init__.py (create_app FastAPI factory).

Originally written in Lot 4 as characterization tests documenting two gaps:
private-container access (`pipeline._c...`) and a routing bug that made
`POST /answer` return 422 on every documented call. Lot 8
(docs/refactoring-plan.md) fixed both — `RAGEngine.manifest_id` is now a
public property, and `QuestionRequest`/`AnswerResponse` moved to module
level (the routing bug was `from __future__ import annotations` combined
with locally-scoped classes breaking FastAPI's forward-reference
resolution). These are now regression tests, not characterization: `git
log` this file, or docs/refactoring/lot-8-native-adapter.md, for the
before/after.

Still-open gaps (not this lot's job): raw exception leakage and the
absence of authentication — both still real, covered below, owned by
Lot 16a.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import modular_rag.api as api_module
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk


class _FakePipeline:
    def __init__(self, *, answer_error: Exception | None = None) -> None:
        self.manifest_id = "fake-pipeline"
        self._answer_error = answer_error

    def answer(self, question: str) -> Answer:
        if self._answer_error is not None:
            raise self._answer_error
        return Answer(query_id=new_id(), text=f"answer to: {question}", trace_id="trace-123")

    def retrieve(self, question: str, k: int = 10) -> list[RetrievedChunk]:
        chunk = Chunk(doc_id=new_id(), content="x" * 500)
        return [RetrievedChunk(chunk=chunk, score=0.9, rank=1)]


def _client(pipeline: _FakePipeline, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api_module, "load_pipeline", lambda path: pipeline)
    app = api_module.create_app("unused-manifest-path.yaml")
    return TestClient(app)


def test_health_reads_pipeline_id_via_public_property(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_FakePipeline(), monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pipeline": "fake-pipeline"}


def test_answer_accepts_the_documented_json_body_and_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for the Lot 4 routing bug (fixed in Lot 8): moving
    QuestionRequest/AnswerResponse to module level lets FastAPI resolve the
    `from __future__ import annotations`-postponed forward reference."""
    client = _client(_FakePipeline(), monkeypatch)

    response = client.post("/answer", json={"question": "What is RAG?"})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "answer to: What is RAG?"
    assert body["trace_id"] == "trace-123"
    assert body["citations"] == []


def test_answer_leaks_raw_exception_text_on_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Still a real gap (Lot 16a owns it, not this lot): internal exception
    strings reach the HTTP response body verbatim via `detail=str(exc)`."""
    client = _client(
        _FakePipeline(answer_error=RuntimeError("db password is hunter2")), monkeypatch
    )

    response = client.post("/answer", json={"question": "hi"})

    assert response.status_code == 500
    assert "hunter2" in response.json()["detail"]


def test_retrieve_truncates_chunk_content_to_300_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_FakePipeline(), monkeypatch)

    response = client.get("/retrieve", params={"q": "test", "k": 5})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert len(body[0]["content"]) == 300


def test_no_authentication_is_required_on_any_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known gap: zero auth on any route. Fixed at Lot 16a, not here."""
    client = _client(_FakePipeline(), monkeypatch)

    assert client.get("/health").status_code == 200
    assert client.post("/answer", json={"question": "hi"}).status_code == 200
    assert client.get("/retrieve", params={"q": "hi"}).status_code == 200
