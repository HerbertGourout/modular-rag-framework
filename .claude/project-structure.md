```
src/modular_rag/
  core/           → enums, ids, errors, Pydantic models (Document, Chunk, Query…)
  contracts/      → typing.Protocol interfaces for every capability
  adapters/       → external bindings (embeddings, vectorstores, llms, auth…)
  ingestion/      → parsers, normalizers, enrichers, chunkers
  retrieval/      → BM25, vector, hybrid RRF, rerankers, planners
  generation/     → OpenAI + Anthropic generators, citations, groundedness
  security/       → guard, adversarial detector, PII redactor, policy engine
  agents/         → coordinator, planner, retriever, extractor, synthesizer, validator
  memory/         → KV store, knowledge graph, EvoRAG versioning
  eval/           → exact-match, retrieval metrics, benchmark runner
  observability/  → StructlogTelemetry, NullTelemetry
  orchestration/  → RAGEngine, ComponentRegistry, QueryRouter, FlowCompiler, StateMachine
  app/            → bootstrap, container (DI), settings (MRAG_* env vars), lifecycle
  cli/            → mrag ask / ingest / version  (Typer)
  api/            → FastAPI create_app(), /health /answer /retrieve

manifests/presets/   → 5 YAML pipeline configs (V1→V5)
tests/unit/          → fast, no external services
tests/contract/      → isinstance(obj, Protocol) conformance checks
tests/integration/   → requires Qdrant on localhost:6333
tests/e2e/           → full pipeline with real LLM (not yet written)
docs/architecture/   → overview, data-model, module-model, runtime-flow, security, structure
```

> Per [ADR-0005](../docs/adr/0005-document-ai-control-plane-boundary.md) (accepted 2026-08-04):
> `agents/`'s coordinator/planner/synthesizer/validator roles are delegated to a selected
> external engine, not built natively — this directory hosts the adapter integration. The
> `memory/` knowledge-graph entry may keep a native *data model*, but graph traversal/reasoning
> execution is delegated; this is contingent on Lot 6 evidence, not decided yet. `adapters/`
> now includes `llms`, `graphstores`, `search` as reachable engine-delegation targets
> (Lots 6/7/15); `auth` remains unassigned pending Lot 11b.
