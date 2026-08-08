```
src/modular_rag/
  core/           → enums, ids, errors, Pydantic models (Document, Chunk, Query…)
  contracts/      → typing.Protocol interfaces for every capability
  adapters/       → external bindings (embeddings, vectorstores, llms, auth…)
  ingestion/      → parsers, normalizers, enrichers, chunkers
  retrieval/      → BM25, vector, hybrid RRF, rerankers
  generation/     → OpenAI + Anthropic generators, citations, groundedness
  security/       → guard, adversarial detector, PII redactor, policy engine, tenant isolation
  agents/         → engine-delegation adapter integration only (ADR-0005 §5.2) — no native
                    agent runtime; the classes this line used to name (coordinator, planner,
                    retriever, extractor, synthesizer, validator) were removed in Lot 17
  memory/         → KV store, knowledge graph (data model retained with a caveat, see below)
  eval/           → exact-match, retrieval metrics, benchmark runner, quality gate
  observability/  → StructlogTelemetry, NullTelemetry
  orchestration/  → RAGEngine, ComponentRegistry, NativeEngineAdapter, PipelineStateMachine,
                    IndexReconciler — see orchestration/CLAUDE.md for the real file list
  app/            → bootstrap, container (DI), settings (declared but not yet wired — see below)
  cli/            → mrag ask / ingest / validate / manifest-schema / version  (Typer)
  api/            → FastAPI create_app(), /health /ready /answer /retrieve

manifests/presets/   → 5 YAML pipeline configs — only local-hybrid-rag.yaml is Runnable end to
                       end; the other four are Blueprint-only (manifests/README.md)
tests/unit/          → fast, no external services
tests/contract/      → isinstance(obj, Protocol) conformance checks
tests/integration/   → requires Qdrant on localhost:6333
tests/e2e/           → full pipeline with real LLM (not yet written)
docs/architecture/   → overview, data-model, module-model, runtime-flow, security, structure
```

> Per [ADR-0005](../docs/adr/0005-document-ai-control-plane-boundary.md) (accepted 2026-08-04):
> `agents/`'s coordinator/planner/synthesizer/validator roles are delegated to a selected
> external engine, not built natively — this directory hosts the adapter integration (not yet
> written) rather than a native runtime; the five prototype classes it once held were removed
> in Lot 17 (`docs/refactoring-plan.md`) for having zero test coverage and zero consumers. The
> `memory/` knowledge-graph entry keeps a native *data model*
> (`memory/graph/knowledge_graph.py`), retained with a documented caveat — whether its
> multi-hop-traversal methods count as "data model" or delegated "traversal execution" remains
> genuinely undecided; Lot 6's spike never produced evidence bearing on this specific question.
> `adapters/` includes `llms`, `graphstores`, `search` as reachable engine-delegation targets
> (Lots 6/7/15); `auth` hosts a real Keycloak `TokenVerifier` implementation (Lot 11b) and is no
> longer unassigned. `app/settings.py`'s `Settings` class (`MRAG_*` env vars) is declared but
> never actually constructed anywhere in the real pipeline-wiring path — found in Lot 16c
> (`docs/refactoring/lot-16c-deployment-runbooks.md`), not yet fixed; don't assume any `MRAG_*`
> variable configures a running pipeline without checking `app/default_factories.py`
> first.
