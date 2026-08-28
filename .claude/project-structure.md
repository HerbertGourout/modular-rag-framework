```
src/modular_rag/
  core/           → enums, ids, errors, Pydantic models, resilience, pricing
  contracts/      → Protocol ports plus manifest and engine contracts
  adapters/       → Qdrant, Postgres, Keycloak, embedding, LangGraph and OTel bindings
  ingestion/      → text/PDF/DOCX/HTML parsers, normalization, enrichment, chunking, lifecycle
  retrieval/      → in-memory BM25, Qdrant dense/sparse retrieval, hybrid RRF, reranking
  generation/     → OpenAI, Anthropic and deterministic generators, citations, groundedness
  security/       → guard, adversarial detection, redaction, policy, tenant isolation, audit/review
  agents/         → namespace only; no native multi-agent runtime
  memory/         → key/value storage only; no knowledge-graph implementation
  eval/           → exact match, recall/precision/MRR, benchmark runner, quality gate
  observability/  → Structlog/Null telemetry plus NullTracer/NullMeter
  orchestration/  → RAGEngine, registry/container, native adapter, state machine, reconciliation
  app/            → bootstrap, public application service, configuration and admin facades
  cli/            → ask, ingest, validate, reconcile, db, audit, schema and version commands
  api/            → FastAPI /health, /ready, /answer and /retrieve

manifests/presets/     → three runnable manifests: local, secure-enterprise and LangGraph
manifests/blueprints/  → non-loadable GraphRAG and multimodal design sketches
tests/unit/            → service-free unit suite
tests/contract/        → Protocol/schema/boundary conformance
tests/integration/     → live Qdrant and PostgreSQL coverage
tests/e2e/             → deterministic governed pipeline plus scheduled real-LLM pipeline
docs/                  → active architecture/API/guides/operations plus dated historical records
```

The selected engine boundary is real: `NativeEngineAdapter` wraps `RAGEngine`, while
`LangGraphEngineAdapter` runs a fixed route → retrieve → guard → generate `StateGraph`. The latter
does not currently implement planning, tool use, query decomposition or collaborative agents;
those behaviours remain delegated targets under ADR-0005.

`adapters/auth/` contains the real `KeycloakTokenVerifier`. `adapters/graphstores/` and
`adapters/search/` remain empty extension targets.

The former `app/settings.py` and native graph
model were removed; configuration flows through manifests, environment interpolation and
`secret://` resolution.

Observability has three separate surfaces: post-request `Trace`/`Telemetry`, live
OpenTelemetry-compatible `Tracer` spans, and operational `Meter` metrics. The real OTel adapters
live in `adapters/observability/`; no shipped preset enables tracer or meter yet.
