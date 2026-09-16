# Capability Matrix — Current Operational Truth

**Baseline snapshot date:** 2026-08-07 (before ADR-0007's Étapes 4-8 landed).
**Last updated:** 2026-09-11 (Lot 21 — engine-independent assurance contract and conformance
report, corrected after Codex review pass 1).
**Scope:** current repository state, including the ADR-0007 boundary correction and
ADR-0012/ADR-0013/ADR-0014 observability and governance ports.

This matrix is the evidence-based source for whether a capability is actually usable. A class
existing under `src/` is not sufficient: a capability is **operational** only when a supported
entry point can activate it and tests cover that path. The original 2026-08-07 baseline
(before any ADR-0007 fix landed) is preserved in git history (`docs/refactoring-plan.md`'s
commit history around Lot 19) if you need the exact "before" comparison point.

## Reproducible baseline (original snapshot, still accurate as history)

Before the Step-3 checker tests were added, the repository contained 214 Python files and 155
Markdown files. Compilation passed and the local service-free suite reported 548 passing tests
(466 unit + 82 contract). After adding the 27 dependency-policy tests, the same suite reported
575 passing tests. As of the 2026-08-08 finalization pass, the suite reported 593 tests
(503 unit + 90 contract). A later 2026-08-08 intermediate snapshot reported 226 Python files and
717 service-free tests (608 unit + 109 contract). These numbers are retained only as historical
"before" evidence. The 2026-08-26 alignment audit executed the current service-free suite:
**1,185 passed** (1,058 unit + 127 contract); it also collected 69 integration and 15 e2e tests
without running those service-dependent suites. Run
`pytest tests/unit tests/contract --collect-only -q` for the live count rather than treating any
snapshot as a permanent badge.

Built-in manifest factories, current as of this update:

| Role | Registered types |
|---|---|
| `chunker` | `fixed`, `adaptive` |
| `embedder` | `sentence-transformers`, `openai-embeddings`, `deterministic` |
| `indexer` | `qdrant` |
| `retriever` | `vector`, `hybrid`, `sparse-qdrant` |
| `reranker` | `cross-encoder` |
| `generator` | `openai`, `anthropic`, `deterministic` |
| `guard` | `basic` |
| `tenant_policy` | `tenant-isolation` |
| `policy_engine` | `inline` |
| `redactor` | `patterns` |
| `egress_policy` | `manifest`, `opa` |
| `review_queue` | `human-review`, `postgres-human-review` |
| `audit_sink` | `in-memory`, `postgres` |
| `feedback_sink` | `in-memory`, `postgres` |
| `telemetry` | `structlog`, `null` |
| `tracer` | `otel`, `null` |
| `meter` | `otel`, `null` |
| `lifecycle_ledger` | `in-memory`, `postgres` |

The `deterministic` `embedder`/`generator` pair (`DeterministicEmbedder`, `DeterministicGenerator`)
needs no network call or LLM API key — feature-hashing for embeddings, and an answer built
directly from citation passages for generation — and exists specifically so the secure-preset e2e
scenario (`tests/e2e/manifests/secure-deterministic-rag.yaml`) can exercise tenant isolation and
audit end to end without requiring an external credential.

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
| **Proposed** | Documented future direction awaiting an architecture/maintainer decision; no implementation claim. |
| **Not built** | No implementation exists yet, regardless of what design docs describe. |

## Runtime and configuration

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Native ingestion, retrieval and generation | **Operational** | V1 manifest → `load_pipeline()` → `ComponentRegistry.wire()` → `RAGEngine` | `manifests/presets/local-hybrid-rag.yaml`; `tests/e2e/test_simple_qa_pipeline.py` (service-dependent). |
| Engine-neutral native adapter | **Operational** | `load_native_engine()` or `load_engine()` with `engine.adapter: native` | `app/bootstrap.py`; engine conformance tests. |
| LangGraph adapter | **Operational** | `load_engine()` or `load_application()` with `engine.adapter: langgraph`, including `manifests/presets/langgraph-rag.yaml` | Unit/conformance coverage; API and CLI honor the selected adapter. The current graph is a fixed route → retrieve → guard → generate flow, not a multi-agent planner. Raw retrieval remains a native application use case because `DocumentEngine` intentionally exposes answer orchestration, not retrieval-only execution. |
| Existing external-application wrapper | **Planned** | None | Accepted ADR-0015 schedules this for Lot 22. The current LangGraph adapter reconstructs a fixed graph from framework components; it does not wrap an arbitrary existing LangChain/LangGraph application. |
| L0/L1/L2 assurance report | **Operational (Lot 21)** | `DocumentEngine.conformance_report(context)` — implemented by both `NativeEngineAdapter` (delegates to `RAGEngine.conformance_report()`) and `LangGraphEngineAdapter`; optional manifest `assurance.min_level` rejects an unmeetable minimum before `wire()` succeeds | `contracts/assurance.py`: `AssuranceLevel`/`EvidenceStatus`/`EvidenceKind`/`ConformanceReport`, per [ADR-0017](../adr/0017-engine-independent-assurance-contract.md) (Accepted 2026-09-10). `achieved_level` is a computed property, never adapter-asserted. **Evidence, not wiring** (Codex review pass 1): a wired role counts only if it satisfies its contract Protocol, and `RETRIEVAL_PROVENANCE`/`USAGE_COST` are earned only by an actual execution — a report for a request that has not run cannot exceed L0. The `assurance.min_level` startup gate necessarily evaluates a separate *capability* profile (it runs before any request), authoritatively re-checked against the constructed components at the end of `wire()`. That gate promises only that the required controls are **declared, wired and structurally conformant** — Protocol membership cannot prove enforcement, so a structurally valid no-op control passes it ([ADR-0017 §9](../adr/0017-engine-independent-assurance-contract.md), accepted risk 2026-09-11). Enforcement is certified behaviourally instead, by `tests/contract/test_engine_conformance.py`, which grants `ENFORCED` only when a denied or failing control demonstrably fails the request and `VERIFIED` only when fabricated evidence is rejected. LangGraph's own documented Lot 15 audit-emission gap (`AUDIT_COMPLETION` structurally `UNSUPPORTED`) caps it below L2 even with tenant/guard/egress fully wired — honest, not native-equivalent parity. See `docs/refactoring/lot-21-engine-independent-assurance-contract.md` for full scope and residual gaps (Lot 22's existing-application wrapping remains separately planned). |
| Manifest YAML validation | **Operational** | `load_manifest()` / `PipelineManifest.model_validate()` | Unknown top-level fields are rejected (`extra="forbid"`). Legacy fields (`planner`/`agents`/`graph_store`/old-style `policies`/`modalities`) now hard-fail validation instead of being silently ignored (Étape 7). |
| Environment layering, `${VAR}` and `secret://` | **Operational** for `mrag validate` and `load_pipeline()` | `resolve_manifest()`, called by both `mrag validate` and `load_pipeline()` | Verified end-to-end on `secure-enterprise-rag.yaml` (Étape 7): `${QDRANT_URL}`, `secret://QDRANT_API_KEY`, `secret://AUDIT_DATABASE_URL` all resolve. |
| Capability dry-run validation | **Operational, with a known gap** | `mrag validate` → `validate_capabilities()` | Checks most registered runtime roles, tenant-enforcement coherence, engine compatibility, and rejects offline evaluation/gate declarations. It currently omits `observability.tracer` and `observability.meter`; an unknown type can therefore pass dry-run and fail later in `ComponentRegistry.wire()`. |
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
| Distributed tracing (OpenTelemetry) | **Operational, custom manifest** | Manifest `observability.tracer.type: otel` or `null` | ADR-0012. `RAGEngine`-internal spans are native-only; engine-neutral `app.request`/`api.*` spans also work with LangGraph. No shipped preset enables a tracer. |
| Operational metrics (OpenTelemetry) | **Operational, custom manifest** | Manifest `observability.meter.type: otel` or `null` | ADR-0013. Request metrics work with either engine; pipeline-stage metrics are native-only. No shipped preset enables a meter. Read the sampling limitations in `docs/observability/` before deploying the reference alerts. |
| Human review queue | **Operational (native)** | Manifest `governance.review_queue.type: human-review` or `postgres-human-review` | Consumed by `RAGEngine`; rejected with LangGraph today. `postgres-human-review` (ADR-0014, Batch 14) is the durable backend; `mrag review list-pending`/`resolve`/`purge`/`count-expired` are the CLI operations against it. |
| User feedback collection | **Operational (native)** | Manifest `governance.feedback_sink.type: in-memory` or `postgres`; `POST /feedback` | ADR-0014 (Batch 14). Consumed by `RAGEngine.record_feedback()`; rejected with LangGraph today, same ADR-0008 boundary as `audit_sink`/`review_queue`. `correction_text` requires a wired `governance.redactor` or the call is refused. `mrag feedback purge`/`count-expired` for retention. |
| Document lifecycle and erasure | **Operational** | Manifest `lifecycle.ledger.type: in-memory` or `postgres` | Both registered (Postgres added Étape 6); engine methods tested. |
| Index reconciliation | **Operational through CLI and Python** | `mrag reconcile --mode check|repair` or construct `IndexReconciler` | Not exposed through the HTTP API or a manifest role; the CLI resolves the selected pipeline and executes check/repair. |
| Exact-match evaluator | **Programmatic only** | Construct `ExactMatchEvaluator` for an offline benchmark | Contract/unit-tested. It requires an expected answer and is intentionally rejected in runnable pipeline manifests. |
| Golden-set benchmark runner | **CI-gated CLI script** | `python scripts/run_benchmark.py [--enforce]`; `.github/workflows/ci.yml`'s `benchmark-gate` job | Batch 13 (external plan). Ships one populated, synthetic, `default`-domain golden set (`eval/datasets/core_v1.yaml`, 13 cases: 9 QA + 4 safety probes) against a deterministic manifest (no LLM key). Scores retrieval (recall/precision/MRR/NDCG, from `Answer.citations`), faithfulness/answer-correctness (deterministic lexical proxies, not an LLM judge), safety-probe pass rate, latency, and best-effort cost. See `docs/guides/offline-evaluation.md`. |
| Quality gates | **Programmatic, CI-enforced** | Apply `QualityGate` to offline benchmark metrics; `scripts/run_benchmark.py --enforce` runs it in `blocking` mode against `eval/reports/baseline.json` | Unit-tested `report_only`/`blocking` behavior, now also supports `lower_is_better` metrics (cost/latency). Intentionally rejected in runnable pipeline manifests; see ADR-0008. Current baseline thresholds are a documented, deliberately lenient floor pending a real calibration run (no live Qdrant in this environment) — see the guide above. |
| Data-classification vocabulary | **Operational (Lot 20)** | `Document.classification`/`Chunk.classification`, propagated by every registered `Chunker`; read by `governance.egress_policy` | Explicit, caller-supplied only — this codebase still does not infer a classification from content. `None` (unclassified) is never treated as `PUBLIC`. |
| Provider data-egress control | **Operational, mandatory for known remote providers (Lot 20)** | Manifest `governance.egress_policy.type: manifest` (config `providers`/`default_classification`) or `type: opa` (decision delegated to an Open Policy Agent server since 2026-09-14; `providers` still declares coverage and which providers are local, and OPA receives only the classification, provider type and operation, never content); consumed before `Embedder.embed()` for both document/chunk ingestion and query-time embedding at retrieval, `Reranker.rerank()`, and `Generator.generate()`, on both the native and LangGraph engines | Fail-closed: a manifest wiring one of this framework's own known remote provider types (`openai`, `anthropic`, `openai-embeddings`) with no `governance.egress_policy` covering it is rejected before `wire()` succeeds — silence is not permission. Purely local pipelines (`sentence-transformers`/`deterministic`/`cross-encoder` only) need no configuration. All three shipped presets now configure it (`max_classification: restricted`, preserving prior behavior since no real classification data flows through them yet). `EgressDeniedError` (a `SecurityError`) maps to HTTP 403 / CLI exit 3 automatically. See `docs/refactoring/lot-20-data-classification-egress-control.md` for full scope and residual gaps ([ADR-0016](../adr/0016-provider-egress-control.md) Accepted 2026-09-09; no pseudonymization). Under `type: opa`, a credential is refused over cleartext HTTP outside a loopback host, and the critical readiness probe evaluates the configured decision document rather than OPA's `/health`, so an absent or unauthorized decision path turns `/ready` unready instead of reporting a false green (Codex review pass 1, HIGH-001/HIGH-002). |
| Cost/latency evidence reporting (V3.1) | **Partially operational** | Custom manifest with `observability.meter.type: otel`; reference Grafana dashboard | Aggregate request latency, token and static estimated-cost series exist. Per-query/user/month attribution, a cost-reporting module and anomaly detection do not. |
| Drift detection / eval trigger (V3.2) | **Offline script, real and unit-tested** | `python scripts/run_drift_check.py --manifest <path> [--baseline <path>]` | ADR-0014 (Batch 14). `eval/drift_detection.py` is pure (no manifest/DB access itself); never manifest-activated (ADR-0008). No historical baseline from real production traffic exists yet — `--update-baseline` establishes one. `should_trigger_retraining` is an advisory flag nothing currently consumes. See `docs/guides/feedback-and-drift.md`. |

## Delegated, removed, and future capabilities

| Capability | Status | Activation path today | Evidence / limitation |
|---|---|---|---|
| Generic multi-agent orchestration | **Delegated target, unavailable today** | Future external engine through `DocumentEngine` | Native prototypes were removed in Lot 17. `langgraph-rag.yaml` proves adapter selection but its current graph is fixed and contains no planning, tools or collaborating agents. |
| GraphRAG traversal | **Delegated** | Intended external-engine capability, not available in LangGraph today | `manifests/blueprints/graph-memory-rag.yaml` documents the sketch; not loadable. |
| Native knowledge-graph data model | **Removed** (Étape 8, resolves ADR-0007's open decision #4) | None — `memory/graph/` no longer exists | Zero consumers anywhere outside its own test; `neighbours()`/`subgraph_for_query()` were genuine traversal logic, not passive storage. Restorable via git history. |
| Fine-tuning execution | **Delegated** | External MLOps tooling | Native ownership is limited to drift detection/evaluation triggers, which are now real (see the V3.2 row above) but not wired to any actual external retraining trigger. |
| Multimodal execution | **Delegated** | Future external-engine adapter capability | `manifests/blueprints/multimodal-rag.yaml` is a non-runnable sketch. Native ownership is limited to a future decision about provenance, citations, classification, and egress—not VLM inference. |
| Multilingual quality and jurisdiction-aware governance | **Not built** | None | No `adapters/nlp/` module exists. Jurisdiction must come from trusted deployment/tenant/legal context, never inferred from query language alone. |

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
8. `IndexReconciler` is available through CLI/Python but not through the HTTP API or manifests.
9. Audit, telemetry, policy-engine and human-review bridging above the delegated-engine boundary
   remains unimplemented; incompatible LangGraph manifests now fail startup rather than no-op.
