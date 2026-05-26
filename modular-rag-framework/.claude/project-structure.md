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
