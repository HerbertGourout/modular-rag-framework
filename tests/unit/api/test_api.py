"""Characterization tests for api/__init__.py (create_app FastAPI factory).

Uses a fake pipeline (monkeypatched load_pipeline) to characterize routes
without touching real adapters. Also captures gaps already tracked in
docs/refactoring-plan.md §2 ("API security") — private-container access and
raw exception leakage — plus one **newly discovered** gap not yet in that
table: POST /answer does not actually accept the documented JSON body at
all. See test_answer_route_does_not_accept_the_documented_json_body below
for the root cause. None of this is fixed here (Lot 4 characterizes;
Lot 8/16a fix); the new /answer finding should be added to
docs/refactoring-plan.md §2 as part of this lot's evidence.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import modular_rag.api as api_module
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk


class _FakeManifest:
    id = "fake-pipeline"


class _FakeContainer:
    manifest = _FakeManifest()


class _FakePipeline:
    def __init__(self, *, answer_error: Exception | None = None) -> None:
        self._c = _FakeContainer()
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


def test_health_reads_pipeline_id_via_private_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(_FakePipeline(), monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pipeline": "fake-pipeline"}


def test_answer_route_does_not_accept_the_documented_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Newly discovered, not yet in docs/refactoring-plan.md §2.**

    `api/__init__.py` has `from __future__ import annotations` at module
    level *and* defines `QuestionRequest`/`AnswerResponse` as classes local
    to `create_app()`. Under postponed evaluation, the route signature
    `def answer(req: QuestionRequest)` is stored as the bare *string*
    `'QuestionRequest'`. FastAPI tries to resolve that forward reference
    against the function's module globals — where a locally-scoped class
    doesn't exist — fails, and falls back to treating `req` as a required,
    unresolvable query parameter. POSTing the documented `{"question": "..."}`
    body therefore returns 422, not 200: the endpoint has likely never
    worked end-to-end via HTTP. (Forcing `req` as a query param instead
    doesn't help either — it then raises an unhandled
    `pydantic.errors.PydanticUserError: ...ForwardRef('QuestionRequest')...
    is not fully defined`, a 500 with no try/except around it.)
    """
    client = _client(_FakePipeline(), monkeypatch)

    response = client.post("/answer", json={"question": "What is RAG?"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "req"]


def test_answer_handler_logic_works_and_leaks_raw_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler's own logic (unreachable via HTTP today, per the test
    above) is otherwise sound and does what's documented — including the
    known exception-leak gap (`detail=str(exc)`, docs/refactoring-plan.md
    §2 "API security"). Calls the endpoint function directly, bypassing
    FastAPI's broken parameter resolution, to characterize this logic in
    isolation from the routing bug.
    """
    from fastapi import HTTPException

    monkeypatch.setattr(
        api_module, "load_pipeline", lambda path: _FakePipeline(answer_error=None)
    )
    ok_app = api_module.create_app("unused-manifest-path.yaml")
    ok_route = next(r for r in ok_app.routes if getattr(r, "path", None) == "/answer")
    happy_result = ok_route.endpoint(SimpleNamespace(question="What is RAG?"))
    assert happy_result.text == "answer to: What is RAG?"
    assert happy_result.trace_id == "trace-123"
    assert happy_result.citations == []

    monkeypatch.setattr(
        api_module,
        "load_pipeline",
        lambda path: _FakePipeline(answer_error=RuntimeError("db password is hunter2")),
    )
    err_app = api_module.create_app("unused-manifest-path.yaml")
    err_route = next(r for r in err_app.routes if getattr(r, "path", None) == "/answer")
    with pytest.raises(HTTPException) as exc_info:
        err_route.endpoint(SimpleNamespace(question="hi"))
    assert exc_info.value.status_code == 500
    assert "hunter2" in exc_info.value.detail


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
    """Known gap: zero auth on any route — every response below is a routing
    or business-logic status, never 401/403. Fixed at Lot 16a, not here.
    /answer is 422 because of the separate routing bug above, not because
    of any auth check.
    """
    client = _client(_FakePipeline(), monkeypatch)

    assert client.get("/health").status_code == 200
    assert client.post("/answer", json={"question": "hi"}).status_code == 422
    assert client.get("/retrieve", params={"q": "hi"}).status_code == 200
