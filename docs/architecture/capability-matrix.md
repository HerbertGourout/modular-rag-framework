# Capability Matrix — Current Operational Truth

**Baseline snapshot date:** 2026-08-07 (before ADR-0007's Étapes 4-8 landed).
**Last updated:** 2026-08-08 (ADR-0008 — offline evaluation boundary and fail-closed engine
activation).
**Scope:** [ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md)'s
boundary and manifest-activation correction.

This matrix is the evidence-based source for whether a capability is actually usable. A class
existing under `src/` is not sufficient: a capability is **operational** only when a supported
entry point can activate it and tests cover that path. The original 2026-08-07 baseline
(before any ADR-0007 fix landed) is preserved in git history (`docs/refactoring-plan.md`'s
commit history around Lot 19) if you need the exact "before" comparison point.

## Reproducible baseline (original snapshot, still accurate as history)

Before the Step-3 checker tests were added, the repository contained 214 Python files and 155
Markdown files. Compilation passed and the local service-free suite reported 548 passing tests
(466 unit + 82 contract). After adding the 27 dependency-policy tests, the same suite reported
575 passing tests. As of the 2026-08-08 finalization pass, the suite reports 593 tests
(503 unit + 90 contract).

Built-in manifest factories, current as of this update:

| Role | Registered types |
|---|---|
| `chunker` | `fixed`, `adaptive` |
| `embedder` | `sentence-transformers`, `openai-embeddings` |
| `indexer` | `qdrant` |
| `retriever` | `vector`, `hybrid` |
| `reranker` | `cross-encoder` |
| `generator` | `openai`, `anthropic` |
| `guard` | `basic` |
| `tenant_policy` | `tenant-isolation` |
| `policy_engine` | `inline` |
| `redactor` | `patterns` |
| `review_queue` | `human-review` |
| `audit_sink` | `in-memory`, `postgres` |
| `telemetry` | `structlog`, `null` |
| `lifecycle_ledger` | `in-memory`, `postgres` |

`ExactMatchEvaluator` and `QualityGate` are built-in Python evaluation utilities, not manifest
factories. They require golden answers or aggregate benchmark metrics and are therefore used by
the offline evaluation plane.

The `planner` and `graph_store` registry roles (legacy placeholders, never had a registered
factory) were removed from `ComponentRegistry` in Étape 8.

## Status vocabulary

| Status | Meaning |
|---|---|
| **Operational** | Reachable through a documented entry point and covered by tests. |
| **Programmatic only** | Implemented and tested, but requires direct Python construction or injection. |
| **Construction only** | The manifest builds an object, but the normal request path does not consume it. |
| **Blueprint** | Design input only; not expected to execute successfully or completely. |
| **Delegated** | Owned by an external engine/tool behind a repository contract or adapter. |
| **Decision open** | Retention or ownership is unresolved and must not be presented as committed. |
| **Not built** | No implementation exists yet, regardless of what design docs describe. |

## Runtime and configuration

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Native ingestion, retrieval and generation | **Operational** | V1 manifest → `load_pipeline()` → `ComponentRegistry.wire()` → `RAGEngine` | `manifests/presets/local-hybrid-rag.yaml`; `tests/e2e/test_simple_qa_pipeline.py` (service-dependent). |
| Engine-neutral native adapter | **Operational** | `load_native_engine()` or `load_engine()` with `engine.adapter: native` | `app/bootstrap.py`; engine conformance tests. |
| LangGraph adapter | **Operational** | `load_engine()` or `load_application()` with `engine.adapter: langgraph`, including `manifests/presets/langgraph-rag.yaml` | Unit/conformance coverage; API and CLI import `load_application()` through `app.public` and therefore honor the selected adapter. Raw retrieval remains a native application use case because `DocumentEngine` intentionally exposes answer orchestration, not retrieval-only execution. |
| Manifest YAML validation | **Operational** | `load_manifest()` / `PipelineManifest.model_validate()` | Unknown top-level fields are rejected (`extra="forbid"`). Legacy fields (`planner`/`agents`/`graph_store`/old-style `policies`/`modalities`) now hard-fail validation instead of being silently ignored (Étape 7). |
| Environment layering, `${VAR}` and `secret://` | **Operational** for `mrag validate` and `load_pipeline()` | `resolve_manifest()`, called by both `mrag validate` and `load_pipeline()` | Verified end-to-end on `secure-enterprise-rag.yaml` (Étape 7): `${QDRANT_URL}`, `secret://QDRANT_API_KEY`, `secret://AUDIT_DATABASE_URL` all resolve. |
| Capability dry-run validation | **Operational**, extended | `mrag validate` → `validate_capabilities()` | Checks registered runtime roles, tenant-enforcement coherence, engine compatibility, and rejects offline evaluation/gate declarations in runnable manifests. |
| Legacy `planner`, `agents`, `graph_store`, `policies`, `modalities` fields | **Removed from the active schema** | Rejected by `PipelineManifest.model_validate()` | Only present in `manifests/blueprints/*.yaml`, which are never loaded through `resolve_manifest()` (Étape 7). |

## Owned control-plane capabilities

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Basic query/answer guard | **Operational** | Manifest `security.type: basic` | Registered, consumed by `RAGEngine`. |
| PII/secret redaction | **Operational** | Manifest `governance.redactor.type: patterns` | Registered factory + manifest role (Étape 6); used in `secure-enterprise-rag.yaml`. |
| Policy-as-code evaluation | **Operational** | Manifest `governance.policy_engine.type: inline`, policies declared inline in `config.policies` | Registered factory + manifest role (Étape 6); used in `secure-enterprise-rag.yaml`. |
| Tenant isolation | **Operational** | Manifest `governance.tenant_policy.type: tenant-isolation`, gated by explicit `governance.tenant_enforcement: true` | Registered factory + manifest role; `tenant_enforcement=true` without `tenant_policy` now fails validation instead of silently no-op'ing (Étape 6/8). |
| OIDC/Keycloak identity verification | **Programmatic only** (by design) | Pass a `TokenVerifier` to `create_app()` | ADR-0007 explicitly keeps this a service/interface concern, not a manifest-wired domain policy — mixing identity verification with policy enforcement is what the ADR warns against. |
| Structured audit events | **Operational (native)** | Manifest `governance.audit_sink.type: in-memory` or `postgres` | Consumed by `RAGEngine`. LangGraph manifests declaring an audit sink fail startup until an engine-independent bridge exists. |
| Trace telemetry | **Operational (native)** | Manifest `observability.telemetry.type: structlog` or `null` | Consumed by `RAGEngine`. LangGraph manifests declaring telemetry fail startup. |
| Human review queue | **Operational (native)** | Manifest `governance.review_queue.type: human-review` | Consumed by `RAGEngine`; rejected with LangGraph today. |
| Document lifecycle and erasure | **Operational** | Manifest `lifecycle.ledger.type: in-memory` or `postgres` | Both registered (Postgres added Étape 6); engine methods tested. |
| Index reconciliation | **Programmatic only** | Construct `IndexReconciler` with a configured container | Still not exposed through CLI/API or manifests — unchanged by this update. |
| Exact-match evaluator | **Programmatic only** | Construct `ExactMatchEvaluator` for an offline benchmark | Contract/unit-tested. It requires an expected answer and is intentionally rejected in runnable pipeline manifests. |
| Golden-set benchmark runner | **Programmatic only** | Construct `BenchmarkRunner` | Implemented and unit-tested; no shipped golden-set catalogue (`eval/datasets/` is empty) or user-facing runner. |
| Quality gates | **Programmatic only** | Apply `QualityGate` to offline benchmark metrics | Unit-tested `report_only`/`blocking` behavior. Intentionally rejected in runnable pipeline manifests; see ADR-0008. |
| Data-classification vocabulary | **Construction only** | `DataClassification` enum and fixtures | No classification-aware policy enforcement consumes the values — unchanged by this update. |
| Cost/latency evidence reporting (V3.1) | **Not built** | None | `eval/cost_reporting/` doesn't exist on disk. |
| Drift detection / eval trigger (V3.2) | **Not built** | None | `eval/drift_detection.py`/`eval/feedback_collection/` don't exist on disk. |

## Delegated, removed, and future capabilities

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Generic multi-agent orchestration | **Delegated** | External engine through `DocumentEngine` (`manifests/presets/langgraph-rag.yaml`) | Native agent prototypes were removed in Lot 17. `langgraph-rag.yaml` (renamed from `agentic-rag.yaml`, Étape 7) makes delegation the manifest-visible reality instead of a dead `agents:` field. |
| GraphRAG traversal | **Delegated** | Intended external-engine capability, not available in LangGraph today | `manifests/blueprints/graph-memory-rag.yaml` documents the sketch; not loadable. |
| Native knowledge-graph data model | **Removed** (Étape 8, resolves ADR-0007's open decision #4) | None — `memory/graph/` no longer exists | Zero consumers anywhere outside its own test; `neighbours()`/`subgraph_for_query()` were genuine traversal logic, not passive storage. Restorable via git history. |
| Fine-tuning execution | **Delegated** | External MLOps tooling | Native ownership is limited to drift detection/evaluation triggers, which are themselves not built yet (see above). |
| Multimodal execution | **Delegated** | Future external-engine adapter capability | `manifests/blueprints/multimodal-rag.yaml` (moved from `presets/`, Étape 7) is a non-runnable sketch, stripped of its fictional native `agents:`/`graph_store:` blocks; parsing/citation enrichment ownership remains evidence-dependent. |
| Multi-language/cultural reasoning | **Not built** | None | No `adapters/nlp/` module exists; roadmap target only. |

## Known architecture debt — resolved vs. still open

Resolved by Étapes 4-8 (previously listed here as open debt):
1. ~~Layering audit didn't cover `orchestration`/`app`/`api`/`cli`~~ — `scripts/check_layering.py`
   now covers all seven layers, `--strict` passes clean, baseline emptied (Étape 3-4).
2. ~~`orchestration` imports `app.Container`~~ — `Container` moved to `orchestration/container.py`
   (Étape 4).
3. ~~`app/default_factories.py` is the accidental composition root~~ — moved to
   `app/default_factories.py` (Étape 4).
4. ~~Owned runtime control-plane implementations are test-injected, not manifest-wired~~ —
   governance/observability/lifecycle sections are manifest-activatable on the native engine.
   Offline evaluation/gates were removed from runtime wiring by ADR-0008.
5. ~~Runnable presets and non-runnable blueprints share the same folder~~ — split into
   `manifests/presets/` and `manifests/blueprints/` (Étape 7).

6. ~~`RAGEngine` imports lifecycle hashing from the ingestion domain~~ — helpers moved to
   `core/document_identity.py`; the ingestion path keeps only a compatibility re-export.
7. ~~API and CLI bypass `engine.adapter`~~ — both now enter through `load_application()`, which
   resolves the manifest and selects Native or LangGraph before serving answers.

Still open:
8. `IndexReconciler` remains programmatic-only, not exposed through CLI/API/manifests.
9. Audit, telemetry, policy-engine and human-review bridging above the delegated-engine boundary
   remains unimplemented; incompatible LangGraph manifests now fail startup rather than no-op.
