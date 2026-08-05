"""Tests for orchestration/native_engine.py (NativeEngineAdapter, Lot 8).

Proves the adapter (a) conforms to DocumentEngine, (b) produces results in
parity with calling the wrapped RAGEngine directly, and (c) is honest about
what it can't do — capabilities declared empty, governance hook and
cancellation token both correctly ignored rather than silently mishandled,
per the semantics established in tests/contract/test_engine_conformance.py.
"""
from __future__ import annotations

import pytest

from modular_rag.app.container import Container
from modular_rag.contracts.engine import (
    CancellationToken,
    DocumentEngine,
    EngineRequest,
    ExecutionContext,
)
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.errors import EngineCapabilityError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter


class _FakeRetriever:
    def retrieve(self, query, k=10):
        return []

    async def aretrieve(self, query, k=10):
        return []

    def name(self) -> str:
        return "fake-retriever"


class _FakeGenerator:
    def __init__(self) -> None:
        self.last_query: Query | None = None

    def generate(self, query, context, trace) -> Answer:
        self.last_query = query
        return Answer(query_id=query.id, text=f"native answer to '{query.text}'")

    async def agenerate(self, query, context, trace) -> Answer:
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "fake-generator"


def _rag_engine() -> RAGEngine:
    return _rag_engine_and_container()[0]


def _rag_engine_and_container() -> tuple[RAGEngine, Container]:
    manifest = PipelineManifest(
        id="native-adapter-test",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", object())
    container.register("indexer", object())
    container.register("retriever", _FakeRetriever())
    container.register("generator", _FakeGenerator())
    return RAGEngine(container), container


def test_native_adapter_implements_document_engine_protocol() -> None:
    assert isinstance(NativeEngineAdapter(_rag_engine()), DocumentEngine)


def test_native_adapter_declares_no_capabilities() -> None:
    """Honest, not a placeholder: RAGEngine has no native streaming,
    cancellation, tool-use, multi-turn, or GovernanceHook-shaped
    interception today — see the module docstring for why."""
    adapter = NativeEngineAdapter(_rag_engine())
    assert adapter.capabilities == frozenset()


def test_run_parity_with_calling_rag_engine_directly() -> None:
    """The actual point of Lot 8: the adapter must not change what the
    native engine does, only how it's addressed."""
    rag_engine = _rag_engine()
    adapter = NativeEngineAdapter(rag_engine)
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")

    direct_answer = rag_engine.answer("What is RAG?")
    adapted_result = adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)

    # Each call generates its own Query/Trace id internally, so trace_ids
    # necessarily differ across two separate invocations — parity is about
    # the *answer text* being identical for an identical question, and both
    # having a trace_id at all, not the ids matching each other.
    assert adapted_result.text == direct_answer.text != ""
    assert adapted_result.metadata.get("trace_id")
    assert direct_answer.trace_id


@pytest.mark.asyncio
async def test_arun_matches_run() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")
    request = EngineRequest(query=Query(text="What is RAG?"))

    sync_result = adapter.run(request, context)
    async_result = await adapter.arun(request, context)

    assert sync_result.text == async_result.text


@pytest.mark.asyncio
async def test_astream_raises_capability_error_since_streaming_is_not_declared() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(tenant_id="t", correlation_id="c", request_id="r")

    with pytest.raises(EngineCapabilityError, match="STREAMING"):
        async for _ in adapter.astream(EngineRequest(query=Query(text="x")), context):
            pass


def test_governance_hook_is_ignored_since_the_capability_is_not_declared() -> None:
    class _AlwaysBlockHook:
        def check(self, step_name, payload):
            from modular_rag.contracts.engine import GovernanceDecision

            return GovernanceDecision(allowed=False, reason="should be ignored")

    adapter = NativeEngineAdapter(_rag_engine())
    context = ExecutionContext(
        tenant_id="t", correlation_id="c", request_id="r", governance_hook=_AlwaysBlockHook()
    )

    result = adapter.run(EngineRequest(query=Query(text="anything")), context)

    assert "should be ignored" not in result.text
    assert "native answer" in result.text


def test_pre_cancelled_token_is_ignored_since_cancellation_is_not_declared() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    token = CancellationToken()
    token.cancel()
    context = ExecutionContext(
        tenant_id="t", correlation_id="c", request_id="r", cancellation_token=token
    )

    result = adapter.run(EngineRequest(query=Query(text="anything")), context)

    assert result.text  # did not raise


def test_run_propagates_execution_context_tenant_id_to_the_underlying_query() -> None:
    """Lot 11b (docs/refactoring-plan.md): "Propagate authenticated identity
    and tenant through ExecutionContext" — `context.tenant_id` must reach
    the `Query` the wrapped `RAGEngine` actually processes, not be dropped
    at the adapter boundary."""
    rag_engine, container = _rag_engine_and_container()
    adapter = NativeEngineAdapter(rag_engine)
    context = ExecutionContext(tenant_id="acme-corp", correlation_id="c", request_id="r")

    adapter.run(EngineRequest(query=Query(text="What is RAG?")), context)

    assert container.generator.last_query.tenant_id == "acme-corp"


def test_name_and_version_are_non_empty() -> None:
    adapter = NativeEngineAdapter(_rag_engine())
    assert adapter.name() == "native"
    assert isinstance(adapter.engine_version(), str) and adapter.engine_version()
