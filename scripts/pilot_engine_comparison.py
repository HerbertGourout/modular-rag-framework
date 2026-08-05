"""Sanitized representative pilot scenario (Lot 18, docs/refactoring-plan.md — "Run a
sanitized representative scenario with native and external engines under the same governance
and quality profiles. Compare delivery effort, quality, latency, cost, audit evidence,
concurrency, deployment, data migration, and rollback.").

Runs an identical set of synthetic (non-sensitive) queries through both `DocumentEngine`
adapters (`NativeEngineAdapter`, Lot 8; `LangGraphEngineAdapter`, Lot 15) against the *same*
wired `Container` — same guard, same tenant policy, same fake retriever/generator — and prints
a side-by-side comparison. Deliberately uses real, in-process fake components (not live
OpenAI/Anthropic/Qdrant) rather than a live LLM/vector-store call: this environment has no API
keys or reachable Qdrant to run a genuinely live scenario against, and "sanitized" already rules
out real customer data. What this script *does* prove for real: both adapters run the identical
governance path (tenant isolation, guard denial) to identical outcomes, and their declared
capabilities differ exactly where Lot 15's decision record says they should. What it does *not*
prove: real LLM answer quality or Qdrant-scale latency/cost — those need a live deployment (see
docs/refactoring/lot-18-pilot-and-closure.md for the honest accounting of what this script can
and cannot demonstrate).

Usage: python scripts/pilot_engine_comparison.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from modular_rag.app.container import Container
from modular_rag.contracts.engine import EngineRequest, ExecutionContext
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.errors import SecurityError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.orchestration.engine import RAGEngine
from modular_rag.orchestration.native_engine import NativeEngineAdapter
from modular_rag.security.filters.basic_guard import BasicSecurityGuard
from modular_rag.security.policies.tenant_isolation import TenantIsolationPolicy


class _FakeRetriever:
    """Deterministic, no-network stand-in for a real Retriever (Lot 18 pilot only)."""

    def __init__(self) -> None:
        self._chunks = [
            Chunk(doc_id="doc-1", content="Hybrid retrieval fuses BM25 and vector search via RRF.", tenant_id="acme"),
            Chunk(doc_id="doc-2", content="Tenant isolation denies cross-tenant chunk access.", tenant_id="acme"),
        ]

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(chunk=c, score=0.9 - 0.1 * i, rank=i + 1, retrieval_method=RetrievalMethod.HYBRID)
            for i, c in enumerate(self._chunks[:k])
        ]


class _FakeGenerator:
    """Deterministic, no-network stand-in for a real Generator (Lot 18 pilot only)."""

    def generate(self, query: Query, context: list[RetrievedChunk], trace: object) -> Answer:
        return Answer(
            query_id=query.id,
            text=f"[pilot-fake answer to: {query.text!r}] grounded in {len(context)} chunk(s).",
            citations=[],
        )


def _pilot_container(*, tenant_id: str | None) -> Container:
    manifest = PipelineManifest(id="lot-18-pilot", generator=ComponentConfig(type="openai"))
    container = Container(manifest)
    container.register("retriever", _FakeRetriever())
    container.register("generator", _FakeGenerator())
    container.register("guard", BasicSecurityGuard())
    container.register("tenant_policy", TenantIsolationPolicy())
    return container


@dataclass
class _Result:
    engine: str
    query: str
    outcome: str
    latency_ms: float
    steps: list[str]
    capabilities: frozenset[str]


def _run_both_engines(question: str, tenant_id: str | None) -> list[_Result]:
    container = _pilot_container(tenant_id=tenant_id)
    native = NativeEngineAdapter(RAGEngine(container))

    from modular_rag.adapters.llms.langgraph_engine import LangGraphEngineAdapter

    langgraph = LangGraphEngineAdapter(container)

    request = EngineRequest(query=Query(text=question, tenant_id=tenant_id))
    context = ExecutionContext(tenant_id=tenant_id, correlation_id="pilot", request_id="pilot")

    results: list[_Result] = []
    for name, engine in [("native", native), ("langgraph", langgraph)]:
        t0 = time.perf_counter()
        try:
            result = engine.run(request, context)
            outcome = f"OK: {result.text[:60]!r}"
            steps = [s.name for s in result.steps]
        except SecurityError as exc:
            outcome = f"DENIED: {exc}"
            steps = []
        latency_ms = (time.perf_counter() - t0) * 1000
        results.append(
            _Result(
                engine=name,
                query=question,
                outcome=outcome,
                latency_ms=latency_ms,
                steps=steps,
                capabilities=frozenset(c.value for c in engine.capabilities),
            )
        )
    return results


def main() -> None:
    scenarios = [
        ("What is hybrid retrieval?", "acme"),
        ("Explain tenant isolation.", None),  # no tenant_id -> tenant_policy should deny both
    ]

    print("Lot 18 pilot: native vs. langgraph DocumentEngine, identical governance path\n")
    for question, tenant_id in scenarios:
        print(f"--- Query: {question!r}  (tenant_id={tenant_id!r}) ---")
        for r in _run_both_engines(question, tenant_id):
            print(f"  [{r.engine:9s}] {r.outcome}")
            print(f"               latency={r.latency_ms:.3f}ms steps={r.steps}")
            print(f"               capabilities={sorted(r.capabilities)}")
        print()


if __name__ == "__main__":
    main()
