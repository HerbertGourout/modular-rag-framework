# Capability Matrix — Current Operational Truth

**Snapshot date:** 2026-08-07  
**Scope:** repository behavior before the boundary and manifest refactors proposed in
[ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md).

This matrix is the evidence-based source for whether a capability is actually usable. A class
existing under `src/` is not sufficient: a capability is **operational** only when a supported
entry point can activate it and tests cover that path.

## Reproducible baseline

Before the Step-3 checker tests were added, the repository contained 214 Python files and 155
Markdown files. Compilation passed and the local service-free suite reported 548 passing tests
(466 unit + 82 contract). After adding the 27 dependency-policy tests, the same suite reports
575 passing tests.

The complete layering policy exposes 25 current import violations. They are listed explicitly in
`.claude/layering-baseline.txt`: normal mode rejects any new violation, while `--strict` remains
red until Step 4 removes the recorded debt.

Built-in manifest factories at this snapshot are limited to:

| Role | Registered types |
|---|---|
| `chunker` | `fixed`, `adaptive` |
| `embedder` | `sentence-transformers`, `openai-embeddings` |
| `indexer` | `qdrant` |
| `retriever` | `vector`, `hybrid` |
| `reranker` | `cross-encoder` |
| `generator` | `openai`, `anthropic` |
| `guard` | `basic` |
| `evaluator` | `exact-match` |

The empty `planner` and `graph_store` registry roles are legacy placeholders, not capabilities.

## Status vocabulary

| Status | Meaning |
|---|---|
| **Operational** | Reachable through a documented entry point and covered by tests. |
| **Programmatic only** | Implemented and tested, but requires direct Python construction or injection. |
| **Construction only** | The manifest builds an object, but the normal request path does not consume it. |
| **Blueprint** | Design input only; not expected to execute successfully or completely. |
| **Delegated** | Owned by an external engine/tool behind a repository contract or adapter. |
| **Decision open** | Retention or ownership is unresolved and must not be presented as committed. |

## Runtime and configuration

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Native ingestion, retrieval and generation | **Operational** | V1 manifest → `load_pipeline()` → `ComponentRegistry.wire()` → `RAGEngine` | `manifests/presets/local-hybrid-rag.yaml`; `tests/e2e/test_simple_qa_pipeline.py` (service-dependent). |
| Engine-neutral native adapter | **Operational** | `load_native_engine()` or `load_engine()` with `engine.adapter: native` | `app/bootstrap.py`; engine conformance tests. |
| LangGraph adapter | **Programmatic only** | `load_engine()` with `engine.adapter: langgraph` | Unit/conformance coverage exists, but API and CLI call `load_pipeline()` and therefore do not select it. |
| Manifest YAML validation | **Operational** | `load_manifest()` / `PipelineManifest.model_validate()` | Unknown top-level fields are rejected. Several accepted legacy fields are ignored by wiring; see below. |
| Environment layering, `${VAR}` and `secret://` | **Programmatic only** | `resolve_manifest()` and `mrag validate` | `load_pipeline()` and `load_engine()` call `load_manifest()` directly, so normal startup bypasses resolution. |
| Capability dry-run validation | **Operational for V1 component roles** | `mrag validate` → `validate_capabilities()` | Checks chunker/embedder/indexer/retriever/reranker/generator/guard/evaluator only. |
| Legacy `planner`, `agents`, `graph_store`, `policies`, `modalities` fields | **Blueprint** | Parsed by `PipelineManifest` | `ComponentRegistry.wire()` ignores them; valid YAML can therefore describe behavior that never runs. |

## Owned control-plane capabilities

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Basic query/answer guard | **Operational** | Manifest `security.type: basic` | Registered in `_default_factories.py` and consumed by `RAGEngine`. |
| PII/secret redaction | **Programmatic only** | Register `PatternRedactor` manually on `Container.redactor` | No manifest role or default factory. |
| Policy-as-code evaluation | **Programmatic only** | Construct `PolicyEngine` directly | Not registered, not loaded from `policy_refs`, and not invoked by normal bootstrap. |
| Tenant isolation | **Programmatic only** | Inject `TenantIsolationPolicy` into `Container.tenant_policy` | Enforcement is tested in both engines, but no manifest wiring activates the policy. |
| OIDC/Keycloak identity verification | **Programmatic only** | Pass a `TokenVerifier` to `create_app()` | No manifest/service configuration path; API authentication is optional by default. |
| Structured audit events | **Programmatic only** | Inject an `AuditSink` into `Container.audit_sink` | In-memory and PostgreSQL sinks exist; neither is registered or selected from a manifest. |
| Trace telemetry | **Programmatic only** | Inject `Telemetry` into `Container.telemetry` | Manifest `observability` is parsed but ignored by wiring. |
| Human review queue | **Programmatic only** | Inject `HumanReviewGate` into `Container.review_queue` | No manifest factory or user-facing review workflow. |
| Document lifecycle and erasure | **Programmatic only** | Inject a `LifecycleLedger` | Engine methods are implemented and tested; normal manifests cannot configure a ledger. |
| Index reconciliation | **Programmatic only** | Construct `IndexReconciler` with a configured container | Operational maintenance primitive, not exposed through CLI/API or manifests. |
| Exact-match evaluator construction | **Construction only** | Manifest `evaluation.type: exact-match` | Registry constructs it, but `RAGEngine.answer()` does not run evaluation; `BenchmarkRunner` is the consuming path. |
| Golden-set benchmark runner | **Programmatic only** | Construct `BenchmarkRunner` | Implemented and unit-tested; no shipped golden-set catalogue or user-facing runner. |
| Quality gates | **Programmatic only** | Construct `QualityGate` against a metrics dictionary | Manifest `quality.gates` is parsed but never enforced. |
| Data-classification vocabulary | **Construction only** | `DataClassification` enum and fixtures | No classification-aware policy enforcement consumes the values. |

## Delegated and future capabilities

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Generic multi-agent orchestration | **Delegated** | External engine through `DocumentEngine` | Native agent prototypes were removed in Lot 17. The LangGraph adapter does not make the legacy `agents:` manifest field operational. |
| GraphRAG traversal | **Delegated / decision open** | Intended external-engine capability | `memory/graph/knowledge_graph.py` still contains native multi-hop traversal but has no runtime consumer; retention is unresolved. |
| Native knowledge-graph data model | **Decision open** | Direct Python use only | `GraphNode`/`GraphEdge`/`KnowledgeGraph` have unit tests but no pipeline wiring. |
| Fine-tuning execution | **Delegated** | External MLOps tooling | Native ownership is limited to future drift detection/evaluation triggers. |
| Multimodal execution | **Delegated** | Future external-engine adapter capability | `multimodal-rag.yaml` is a non-runnable blueprint; parsing/citation enrichment ownership remains evidence-dependent. |
| Multi-language/cultural reasoning | **Blueprint** | None | Roadmap target only; no end-to-end implementation or quality evidence. |

## Known architecture debt affecting these statuses

1. The standard layering audit did not cover `orchestration`, `app`, `api`, or `cli` before
   Step 3 of the 2026-08 correction programme.
2. `orchestration` imports `app.Container`, opposite to the published dependency direction.
3. `orchestration/_default_factories.py` acts as the concrete composition root and imports every
   implementation layer; ADR-0007 proposes moving that responsibility to `app`.
4. `RAGEngine` imports lifecycle hashing directly from the ingestion domain.
5. Owned control-plane implementations are mostly test-injected rather than manifest-wired.
6. API and CLI bypass both `load_engine()` selection and `resolve_manifest()` resolution.
7. Runnable presets and non-runnable design blueprints share the same schema and folder.

The target treatment for these items is proposed in ADR-0007. Until its implementation lands,
documentation and client-facing claims should use the statuses in this matrix.
