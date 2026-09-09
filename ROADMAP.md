# Roadmap — Modular RAG V1 → V5 + Strategic Features

> **[ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) (accepted 2026-08-04)
> supersedes part of this roadmap.** V1.1, V1.2, and V2.0 (Policy Engine) are unchanged — built
> natively. **V2.1 (Multi-Agent Teams), V3.0 (GraphRAG), V3.2 (Fine-Tuning Loop mechanics —
> except its drift-detection/evaluation trigger, which stays native), and V5.0 (multimodal
> execution)** are delegated to a selected external engine via the `DocumentEngine` port
> ([ADR-0006](docs/adr/0006-external-engine-selection.md), LangGraph), not built natively. This
> document was reconciled with ADR-0005 on 2026-08-06: the native task lists that used to sit
> under those four items were removed (see
> [Lot 17](docs/refactoring/lot-17-prototype-retirement.md) for the prototype code that
> corresponded to them, where any existed) rather than kept "for historical reference."
>
> **[ADR-0015](docs/adr/0015-portable-assurance-and-external-application-boundary.md) is
> Accepted.** It establishes the next product direction: explicit L0/L1/L2 assurance
> levels and support for wrapping an existing external application without rebuilding its graph.
> Items derived from it are labelled proposed and must not be presented as shipped commitments.

## Version Progression Overview

```
V1: Core RAG Base                              (Q2 2026)
├─ V1.0: Hybrid retrieval + basic security    
├─ V1.1: Evaluation-as-Contract               (NEW)
└─ V1.2: Compliance audit trail               (NEW)

V2: Engine Boundary + Governance              (Q3 2026)
├─ V2.0: Policy engine                        (UPDATED — multi-agent runtime delegated, see V2.1)
└─ V2.1: Multi-agent orchestration            (⚙️ delegated — DocumentEngine port)

V3: Delegated Intelligence + Native Evidence   (Q4 2026)
├─ V3.0: GraphRAG + knowledge graphs          (⚙️ delegated — traversal only; data model TBD)
├─ V3.1: Cost/latency evidence + reporting    (native — routing logic itself is delegated)
└─ V3.2: Drift detection + eval trigger       (native — fine-tuning execution is ⚙️ delegated)

V4: Enterprise + Multilingual Governance       (Q1 2027)
├─ V4.0: Multi-tenant policies + environments
└─ V4.1: Multilingual quality + jurisdiction-aware governance (planned)

V5: Multimodal Evidence                         (Q2 2027)
└─ V5.0: Provenance/citation enrichment (native candidate) — VLM execution ⚙️ delegated

Next assurance programme
├─ Lot 20: Classification + fail-closed provider egress — implemented, mandatory for known remote providers
├─ Lot 21: Engine-independent assurance contract and conformance report (proposed)
└─ Lot 22: Existing-application adapters and cross-engine conformance (proposed)
```

---

This document is the framework's **living development plan**: it lists, version by version,
every planned feature, and the matching checkbox is ticked as soon as the feature is
delivered and covered by tests. Unlike
[docs/architecture/overview.md](docs/architecture/overview.md) (which describes the *target*
architecture, including what isn't built yet), this file reflects the *real* state: an
unchecked box means the feature doesn't reliably exist yet, even if partial code for it
already lives somewhere under `src/`.

**How this document gets updated**: every Pull Request that delivers a feature listed here
ticks the matching checkbox in that same PR — this is a step in the checklist described in
[CONTRIBUTING.md](CONTRIBUTING.md). [CHANGELOG.md](CHANGELOG.md) records the narrative detail
of each change in parallel. For a non-technical explanation of what each version actually
delivers, see [docs/onboarding.md](docs/onboarding.md), section 3.

Versions are not independent batches — each depends on the one before it. V2's engine boundary
and governance build on the retrieval pipeline already built in V1; V3's delegated GraphRAG and
native cost evidence extend that same request path; V4 expands governance already present; and V5
extends ingestion and delegated execution to multimodal inputs. There is no shortcut to an
advanced version without the earlier ones being stable first.

---

## V1 — Core RAG `[V1.0 implemented and live-validated; V1.1/V1.2 partially built]`

**What this version solves**: let a user ask a natural-language question over a document
corpus (PDF, Word, HTML, Markdown, text) and get a sourced answer, without manual search.
This is the foundation everything else builds on — no later version is credible if this one
isn't reliable end to end.

### V1.0 — Hybrid Retrieval + Basic Security

**Core modules:**
- [x] Architectural skeleton (contracts, models, orchestration, manifests)
- [x] Document parsers: PDF, Word, HTML, Markdown, plain text
- [x] Chunkers: fixed-size, adaptive (section-aware)
- [x] Hybrid retrieval: vector (Qdrant) + BM25 fusion (RRF) — code + unit tests done; `tests/integration/` (including the vector-retriever tests) now runs against a real Qdrant service container on every push/PR (Batch 10, `.github/workflows/ci.yml`'s `test-integration` job)
- [x] Cross-encoder reranker
- [x] Generators: OpenAI, Anthropic
- [x] Basic security guard (injection detection, length check, redaction) — `BasicSecurityGuard`, 12 injection patterns across 3 families, real `check_answer()`; see [security.md](docs/architecture/security.md)
- [x] REST API (FastAPI) + CLI (`mrag ask`, `mrag ingest`) — hardened (auth, rate limiting, typed errors) per Lot 16a; see [docs/api/rest.md](docs/api/rest.md)
- [x] Example: `examples/simple_qa/` end-to-end running — script and README verified correct against the real CLI/API; the identical underlying pipeline (same `local-hybrid-rag.yaml` manifest, same `examples/simple_qa/docs/` corpus) now runs nightly against real Qdrant and a real LLM key (`tests/e2e/test_simple_qa_pipeline.py`, Batch 10's `.github/workflows/nightly.yml`) — this confirms the pipeline itself, though not by literally invoking `examples/simple_qa/main.py`'s CLI entry point
- [x] Example: `examples/hybrid_search/`
- [x] `pip install modular-rag[v1]` installs and works — CI's `build-and-smoke-test` job builds a wheel, installs it into a fresh venv, and runs `mrag version` on every push (`.github/workflows/ci.yml`)

**"Done" criterion**: `examples/simple_qa/` genuinely runs end to end (real ingestion, real
retrieval, an answer generated by a real LLM, not a mock), and unit + contract tests pass
without requiring external services for those two categories.

**Success criteria:**
- ✅ End-to-end RAG pipeline implemented and unit/contract-tested; the same pipeline now runs
  nightly against a real LLM + Qdrant (see above) — no longer an unconfirmed live-run gap
- ✅ Security guards pass tests
- ⬜ Hybrid retrieval F1 > 0.75 on golden set — still not measured against real production
  traffic; a small, synthetic golden set now exists and runs in CI (`eval/datasets/core_v1.yaml`,
  Batch 13, see V1.1 below), but its 6-passage corpus is a benchmark fixture, not a
  representative production sample F1 > 0.75 could be claimed against

---

### V1.1 — Evaluation-as-Contract `[NEW — 1 month]`

**Purpose:** Force every component to be measurable; contract-enforced metrics.

**Status: partially built.** The original detailed module list below (`eval/metrics/`,
`eval/golden_sets/`, `eval/regression_dashboard/`) described files that were never actually
created — corrected 2026-08-07 (Étape 9) to describe the real, simpler implementation instead.
Batch 13 (external plan — "Offline benchmark"; not this repo's own `docs/refactoring-plan.md`
Lot numbering) then industrialized it — see
[docs/guides/offline-evaluation.md](docs/guides/offline-evaluation.md).

**What actually exists:**
- `contracts/evaluation.py`: `Evaluator` Protocol (`evaluate(query, answer, expected, context) ->
  Metrics`) — consumed by offline evaluation runners and contract-tested
  (`tests/contract/test_eval_conformance.py`)
- `eval/scorers/exact_match.py`: `ExactMatchEvaluator` — built-in offline answer scorer
- `eval/scorers/retrieval_metrics.py`: `recall_at_k`, `precision_at_k`, `mrr`, `ndcg_at_k`
  (binary-relevance NDCG@k, Batch 13)
- `eval/scorers/faithfulness.py`/`answer_correctness.py` (Batch 13): deterministic lexical-proxy
  scorers for two of the three DIGEST-evaluation.md pairwise generation targets — explicitly not
  LLM-judge (RAGAS/ARES/TRACe-style) scoring, which would need a non-deterministic paid LLM call
- `eval/runners/benchmark.py`: `BenchmarkRunner`/`GoldenSet`/`BenchmarkCase`/`BenchmarkReport` —
  now also classifies failures by `error_stage` (retrieval/generation/security/infra) and scores
  safety-probe cases (`case_type: safety`) separately from QA cases (Batch 13)
- `eval/datasets/core_v1.yaml` + `eval/datasets/loader.py` (Batch 13): one populated,
  synthetic, `default`-domain golden set (13 cases: 9 QA + 4 safety probes) — the first real
  golden set shipped, not yet a *per-domain* catalogue (finance/healthcare/manufacturing golden
  sets remain future work)
- `eval/reporting.py` (Batch 13): JSON + Markdown report writer enabling commit-to-commit
  comparison — a lightweight report, not a live regression-dashboard UI
- `eval/quality_gate.py`: `QualityGate` — compares offline benchmark metrics against a baseline,
  in `report_only` or `blocking` mode; now supports `lower_is_better` metrics (cost/latency,
  Batch 13); not part of runtime pipeline manifests (ADR-0008)
- `scripts/run_benchmark.py` + `.github/workflows/ci.yml`'s `benchmark-gate` job (Batch 13): a
  significant regression past `eval/reports/baseline.json` blocks CI

**Not built:** semantic-similarity/factuality/RAGAS-style (LLM-judge) scorers, per-stratum/
per-cluster golden-set coverage analysis ([2604.20763], DIGEST-evaluation.md #2), and additional
per-domain golden-set YAML files beyond the one `default`-domain set.

**Success criteria:**
- ✅ `Evaluator` Protocol contract-enforced and usable by offline evaluation runners
- ✅ Retrieval metrics (recall/precision/MRR/NDCG) computed
- ✅ NDCG@k
- 🟡 Populated golden sets — one synthetic `default`-domain set ships (Batch 13); per-domain
  (finance/healthcare/manufacturing) sets remain future work
- 🟡 Regression comparison — a JSON+Markdown report + CI-blocking quality gate exist (Batch 13);
  a live dashboard UI does not

---

### V1.2 — Compliance Audit Trail `[NEW — 2 months]`

**Purpose:** GDPR/CCPA-ready logging; prove what happened, when, by whom, with what result.

**Status: partially built.** The original detailed module list below (event schema, data
lineage tracker, access-control log, GDPR/CCPA/HIPAA report generators) described files that
were never actually created — corrected 2026-08-07 (Étape 9) to describe the real, simpler
implementation instead.

**What actually exists:**
- `contracts/audit.py`: `AuditEvent` (structured event model), `AuditEventType`, `AuditSink`
  Protocol
- `security/audit/store.py`: `InMemoryAuditSink` — manifest-wired (`audit_sink: in-memory`)
- `adapters/audit/postgres_sink.py`: `PostgresAuditSink` — durable, append-only (`ON CONFLICT
  DO NOTHING`, no UPDATE/DELETE anywhere in the file), manifest-wired (`audit_sink: postgres`,
  Étape 6)
- `security/redaction/patterns.py`: `PatternRedactor` — manifest-wired (`redactor: patterns`)

**Not built:** a data-lineage tracker (source → processing → response chain as its own
artifact), an access-control log, and GDPR/CCPA/HIPAA report *generators* (nothing produces a
formatted compliance report from the audit events — the events themselves are captured, but
turning them into a report is a manual query today).

**Success criteria:**
- ✅ Structured audit events captured (`AuditEvent`), manifest-activatable sink (in-memory or
  Postgres)
- ✅ PII redaction manifest-activatable (`PatternRedactor`)
- ✅ Postgres audit sink is append-only by construction (no UPDATE/DELETE statements)
- ⬜ Formatted GDPR/CCPA/HIPAA report generation
- ⬜ Explicit data-lineage tracking artifact (source → processing → response)
- ⬜ Access-control log (who accessed what, when, why)

---

## V2 — Agentic + Governance `[Q3 2026]`

**What this version solves**: V1 fails on questions that need several reasoning steps
(cross-referencing multiple facts, double-checking an answer before returning it). A single
call to a language model isn't reliable enough to decompose a complex problem — this version
introduces a team of specialized agents that split up the reasoning steps, with a
self-correction loop when the answer isn't well enough supported by evidence.

### V2.0 — Policy Engine

> **Delegated per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.**
> Multi-agent orchestration (router, coordinator, planner, retriever/extractor/synthesizer/
> validator agents) is delegated to a selected external engine via the `DocumentEngine` port,
> not built natively in this repository. The prototype implementation was removed in
> [Lot 17](docs/refactoring/lot-17-prototype-retirement.md); see that record for what was
> deleted and why. The Policy Engine below is unaffected — it stays native/owned.

**Policy Engine:** `[NEW — P0 priority]`
- `security/policies/`: Policy-as-Code framework
  - `policy_engine.py`: Evaluate queries vs policies before execution
  - `policy_yaml_loader.py`: Load YAML policies (who can access what)
  - `role_based_access.py`: Role-based routing (analyst vs director)
  - `data_classification.yaml`: Sensitivity levels (public, internal, confidential, restricted)
  - `query_routing_policy.yaml`: Route queries to appropriate retrievers/stores
  - `audit_policy.yaml`: Log everything matching criteria
- `orchestration/`: Registry updates
  - `policy_executor.py`: Apply policies before/after retrieval/generation
  - Policies + TraceStep = full auditability
- Multi-tenant support (tenant ID in context, policies per tenant)

**Status: built, with a simpler shape than originally sketched.** Corrected 2026-08-07
(Étape 9) — `policy_loader.py`, `role_based_access.py`, `policy_schemas.py`,
`data_classification/`, `orchestration/policy_executor.py`/`policy_registry.py`, and
`manifests/policies/*.yaml` were never created; policies are declared inline in the manifest's
`governance.policy_engine.config.policies` instead (see `secure-enterprise-rag.yaml`).

**What actually exists:**
```
security/policies/
├── policy_engine.py       (PolicyEngine — evaluate query vs inline Policy objects)
├── tenant_isolation.py    (TenantIsolationPolicy — fail-closed enforce/filter by tenant_id)
└── human_review.py        (HumanReviewGate — hold low-confidence answers for review)
```
All three are manifest-wired (`governance.policy_engine`/`tenant_policy`/`review_queue`) and
contract-tested.

**Success criteria:**
- ✅ Queries evaluated against inline policies before execution (`PolicyEngine`)
- ✅ Multi-tenant isolation working, fail-closed (`TenantIsolationPolicy`)
- ✅ Policy violations raise `PolicyViolationError` (evaluation failures also fail closed, per
  Lot 11b)
- ⚠️ Policy audit trail exists (`AuditEvent`/`AuditSink`) but is not yet a formatted report —
  see V1.2

---

### V2.1 — Multi-Agent Orchestration

> **Delegated per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.**
> Collaborative multi-agent teams (domain specialists, fact-checking, consensus scoring,
> team coordination) are delegated to a selected external engine via the `DocumentEngine` port,
> not built natively in this repository. The prototype implementation was removed in
> [Lot 17](docs/refactoring/lot-17-prototype-retirement.md); see that record for what was
> deleted and why. The selectable `LangGraphEngineAdapter` currently runs a fixed linear RAG
> graph; it does not implement those collaborative behaviours.

---

## V3 — Graph Memory + Intelligence `[Q4 2026]`

**What this version solves**: V1 and V2 retrieve relevant passages of text, but don't model
the relationships between the entities they contain (who depends on whom, what caused what).
Multi-hop questions ("who is affected, in cascade, by this incident?") need a knowledge
graph, not plain text search.

### V3.0 — GraphRAG + Knowledge Graphs

> **Delegated per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.**
> GraphRAG traversal/reasoning execution is delegated to a selected external engine via the
> `DocumentEngine` port; this repository does not implement it natively. The native
> `KnowledgeGraph` data model was removed in Étape 8
> ([ADR-0007](docs/adr/0007-layer-boundaries-and-control-plane-activation.md)) — zero
> consumers anywhere, restorable via git history if a real, wired need emerges.

---

### V3.1 — Cost/Latency Evidence + Reporting `[NEW — 2 months]`

> **Reframed per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.1.** The
> in-house query-routing/model-selection logic this version used to specify (classify
> factual-vs-reasoning, route cheap-vs-expensive models) is delegated to the selected external
> engine — that's generic orchestration mechanics, not a governance concern this framework needs
> to own. What stays native is the **evidence and reporting** layer: cost/latency data collected
> from whichever engine ran the query, surfaced as a dashboard regardless of which engine
> produced the answer.

**Purpose:** Report cost and latency per query, per user, per month — engine-agnostic evidence
for governance and budget decisions, not a routing decision-maker itself.

**Target implementation:**
- `eval/cost_reporting/`: Dashboard
  - Cost per query, per user, per month
  - Trends, anomalies (spike detection)
- `orchestration/`: Record which engine/model actually served each query, for the dashboard to
  attribute cost against

**Modules:**
```
eval/
└── cost_reporting/
    ├── cost_dashboard.py
    └── cost_anomaly_detector.py
```

**Status: partially built.** ADR-0013 adds aggregate OpenTelemetry request latency, generation
token and estimated model-cost metrics, plus a reference Grafana dashboard. The price table is
static, and the signals are not attributed per query, user or month. `eval/cost_reporting/` and an
anomaly detector do not exist. No shipped preset enables the meter; activation currently requires
a custom manifest.

**Success criteria (target, not yet met):**
- ⬜ Cost/latency reported per query, per user, per month, regardless of engine
- ⬜ Anomaly detection flags spikes

---

### V3.2 — Drift Detection + Evaluation Trigger `[NEW — 3 months]`

> **Reframed per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.**
> Fine-tuning *execution* (embedder/reranker retraining, model versioning, A/B rollout) is
> delegated to external MLOps/fine-tuning tooling, not built natively. What stays native is
> **drift detection and the evaluation trigger**: this framework decides *when* quality has
> degraded and *that* retraining should happen; it does not run the retraining itself.

**Purpose:** Collect user feedback, detect quality drift, and trigger an external fine-tuning
process when detected — engine-agnostic evaluation, not an in-house training pipeline.

**Implementation (Batch 14, external plan — "Feedback, drift, and human review"; ADR-0014):**
- `contracts/feedback.py` + `POST /feedback`: gather user signals (thumbs up/down, a
  human-provided correction) durably (`security/feedback/store.py`'s in-memory reference
  implementation, `adapters/feedback/postgres_sink.py`'s durable backend).
- `eval/drift_detection.py`: pure, offline computation over stored feedback, document freshness
  (`LifecycleLedger`), and human-review escalation counts — `compute_drift()` flags a metric that
  degraded past a threshold (`0.02` default, matching this section's own "alert if degrading >
  2%" wording below) and sets an advisory `should_trigger_retraining` flag. Never manifest-
  activated (ADR-0008); a companion script, `scripts/run_drift_check.py`, does the actual
  wire-a-manifest-and-compare work.

**Modules:**
```
contracts/feedback.py                    Feedback, FeedbackSink (real, shipped)
security/feedback/store.py               InMemoryFeedbackSink
adapters/feedback/postgres_sink.py       PostgresFeedbackSink (durable, retention/purge)
adapters/review/postgres_queue.py        PostgresReviewQueue (durable ReviewQueue backend)
eval/drift_detection.py                  pure drift computation (real, shipped)
scripts/run_drift_check.py               offline orchestration script
```

**Status: implemented, not yet calibrated against real production traffic.** Feedback collection,
durable storage/retention, and human-review durability all ship and are unit-tested. Drift
computation is real and pure, but has no historical baseline from real traffic yet — the "alert
if degrading > 2%" threshold is this section's own original target number, not a value tuned
against measured data. See [docs/guides/feedback-and-drift.md](docs/guides/feedback-and-drift.md).

**Explicitly not done** (see ADR-0014's own "Explicitly out of scope" section): automated
re-scoring of feedback carrying a correction (`select_feedback_for_reevaluation()` only selects
candidates — the original answer's full text/citations are not durably persisted anywhere in this
codebase today, so there is nothing yet to re-score against), a reversible pseudonymizer for
feedback free text (destructive redaction via the existing `PatternRedactor` is the shipped
policy), and any actual triggering of an external retraining workflow (the flag is advisory only
— per ADR-0005 §5.2, this framework decides *when*, never runs the retraining itself).

**Success criteria:**
- 🟡 Feedback collection is real and durable; "> 80% of queries" is not measured against any real
  deployment yet.
- ✅ Drift detection computes and flags degradation (`compute_drift()`, unit-tested against
  synthetic snapshots) — not yet run against a real historical baseline.
- 🟡 `should_trigger_retraining` is a real, computed flag; nothing consumes it to actually start
  an external retraining workflow — that integration remains undone by design (delegated,
  ADR-0005 §5.2), not merely unbuilt.

---

## V4 — Multi-Language Governance `[Q1 2027]`

**What this version solves**: a deployment internal to a single team doesn't need formal
governance, but one shared across multiple clients or in a regulated sector (banking,
insurance, healthcare) absolutely does — per-tenant data isolation, proof of auditability,
the ability to hold a risky answer for human review before returning it. This is the version
that makes the framework eligible for regulated enterprise RFPs (see
[docs/business-case.md](docs/business-case.md), section 4).

### V4.0 — Multi-Tenant Policies + Environments

- [x] Inline policy-as-code through manifest rules and `PolicyEngine`
- [ ] OPA-backed policy evaluation
- [ ] Multi-environment manifests (dev/staging/prod)
- [x] Human-in-the-loop review queue for policy-routed answers
- [ ] Risk profile per pipeline
- [ ] Example: `examples/secure_rag/` extended

**Watch point**: tenant isolation, inline policies, redaction, audit sinks and review queuing are
operational primitives. Do not present the broader V4 package — environment promotion, OPA,
risk profiles or formatted compliance reporting — as complete.

---

### V4.1 — Multilingual Quality + Jurisdiction-Aware Governance `[PLANNED]`

**Purpose:** preserve retrieval quality, citations, safety, and user-language fidelity across the
languages required by a deployment without inferring legal or cultural context from language.

**Planned scope:**

- language/script detection as processing metadata, including mixed-script and low-confidence
  results;
- language-aware parsing and chunking where generic segmentation is measurably inadequate;
- multilingual embedding/generation adapters selected through existing contracts and manifests;
- per-language or per-script evaluation slices in versioned golden sets;
- preservation of the user's requested output language, with explicit translation when used;
- locale-aware presentation only when locale is supplied by trusted deployment/user context;
- jurisdiction and regulatory policy supplied explicitly by deployment configuration, tenant
  policy, contractual context, residency, or verified identity attributes.

**Safety boundary:** query language, detected locale, IP address, and model inference must not
select a legal regime by themselves. A French query does not prove French residency or CNIL
jurisdiction; an English query does not distinguish the UK, US, or another jurisdiction. Missing
trusted jurisdiction context must follow the configured fail-closed or human-review policy.

**Status: not yet built.** No `adapters/nlp/` package or multilingual conformance profile exists.
Specific model names and “20+ language” targets must be selected from measured project needs, not
hard-coded into architecture before evaluation.

**Success criteria (target, to baseline per deployment):**

- ⬜ Required-language matrix and golden-set slices approved for the deployment.
- ⬜ Retrieval and answer-quality floors pass for every supported language/script slice.
- ⬜ Mixed-script and wrong-language-output regressions are covered by tests.
- ⬜ Citations remain traceable to the source language and any translation step is evidenced.
- ⬜ Jurisdiction is derived only from trusted policy context, never query language alone.

---

## V5 — Multimodal Evidence `[Q2 2027]`

### V5.0 — Images, Audio, Video, and Table Provenance

> **Delegated per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md) §5.2.** VLM
> execution (image/table/audio/video model inference, modality-specialized agents) is delegated
> to a selected external engine via the `DocumentEngine` port; this repository does not
> implement it natively. The owned candidate is multimodal *evidence*: parsing and stable
> provenance for images, regions, tables, pages, audio timecodes, and video segments, plus data
> classification and egress decisions before those assets reach a VLM. Ownership remains subject
> to an ADR and adapter evidence; no native multimodal implementation exists today.

---

## Timeline & Milestones

These milestones are a higher-level marker than the checkboxes above — they flag the moment a
version becomes "demonstrable" rather than "under construction".

| Version | Target | Key Success Metrics |
|---|---|---|
| **v1.0** | Q2 2026 | ✅ Done — Hybrid RAG working, F1 > 0.75, examples running |
| **v1.1** | Q2 2026 | 🟡 Partial — recall/precision/MRR/NDCG + `Evaluator` contract + one CI-gated golden set shipped (Batch 13); LLM-judge scoring and additional per-domain golden sets not built |
| **v1.2** | Q3 2026 | 🟡 Partial — structured audit events + manifest-activatable sinks shipped; formatted GDPR/CCPA/HIPAA reports not built |
| **v2.0** | Q3 2026 | ✅ Done — `PolicyEngine`/`TenantIsolationPolicy`/`HumanReviewGate` manifest-wired (multi-agent runtime ⚙️ delegated, see v2.1) |
| **v2.1** ⚙️ | Q4 2026 | Delegated target; the current LangGraph adapter proves selection but not multi-agent behaviour |
| **v3.0** ⚙️ | Q4 2026 | Delegated (traversal) — see V3.0 note above |
| **v3.1** | Q1 2027 | 🟡 Partial — aggregate OTel latency/token/cost signals and reference dashboard ship; per-query/user/month reporting and anomaly detection do not |
| **v3.2** | Q1 2027 | 🟡 Implemented but uncalibrated — feedback, durable storage/review, and offline `eval/drift_detection.py` ship; production thresholds and external trigger integration remain |
| **v4.0** | Q1 2027 | 🟡 Core policies/tenant/audit/review primitives shipped; OPA, environments, risk profiles and reporting remain |
| **v4.1** | Q2 2027 | Planned multilingual quality profiles; jurisdiction must come from trusted policy context, not language |
| **v5.0** ⚙️ | Q2 2027 | VLM execution delegated; native provenance/classification/citation enrichment is an unapproved candidate |

⚙️ = delegated to a selected external engine per [ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md), not a native build target for this framework.

---

## Differentiation Hypothesis

LangChain/LangGraph, LlamaIndex, Haystack, MLflow, LangSmith, and cloud platforms already provide
substantial orchestration, evaluation, tracing, and governance capabilities. This roadmap does
not treat their absence as the opportunity. The proposed value is the combination of portable
controls, normalized evidence, explicit capability gaps, and shared conformance across engines.

| Capability | Current state | Strategic treatment |
|---|---|---|
| Native reference RAG | Operational | Keep inspectable and local-first; do not chase orchestration breadth. |
| Evaluation and drift | Operational offline, production calibration incomplete | Retain as portable evidence and release gates. |
| Tenant/policy/audit/review | Broadest on native; partial on LangGraph | Move toward explicit assurance levels instead of claiming uniformity. |
| Multi-agent and GraphRAG | Not provided by current fixed adapter | Delegate to external applications/engines. |
| Data classification and provider egress | Lot 20 implemented, mandatory for known remote providers (`governance.egress_policy`) | All three shipped presets now configure it; [ADR-0016](docs/adr/0016-provider-egress-control.md) for the outbound-data boundary **Accepted 2026-09-09**. |
| Existing-application wrapping | Not built | Proposed Lot 22 after the assurance contract. |
| Multilingual/multimodal | Not built | Focus owned work on quality, provenance, citations, classification, and policy evidence. |

The product thesis remains subject to measured pilots. Shipped controls can support a compliant
deployment, but the framework does not provide turnkey regulatory certification.

---

## References

- **ADR-0001**: Modular architecture with six planes
- **ADR-0002**: Contracts and plugins pattern
- **ADR-0003**: Security and governance (updated with Policy Engine)
- **ADR-0004**: Strategic Features (V1→V5) — superseded (partial) by ADR-0005
- **ADR-0005**: Document-AI control plane product boundary (owned vs. delegated capabilities, accepted 2026-08-04)
- **ADR-0006**: External engine selection — LangGraph (accepted 2026-08-04)
- **ADR-0015**: Portable assurance and external-application boundary (accepted 2026-09-02)
