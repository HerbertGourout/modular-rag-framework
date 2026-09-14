# Changelog

All notable changes are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added — SQuAD experiment script and planned multi-engine benchmark protocol (2026-09-14)

- `scripts/prepare_squad_experiment.py` (new): converts a SQuAD 1.1 JSON file into a deterministic
  golden-set YAML (one paragraph per corpus chunk, first annotated answer per question, `--limit`
  cases) that `scripts/run_benchmark.py --dataset` consumes unchanged. It is an experiment tool,
  not a CI golden set: the SQuAD data and generated YAML are not committed, and `benchmark-gate`
  still runs `core_v1.yaml`.
- [docs/guides/offline-evaluation.md](docs/guides/offline-evaluation.md) gains a **planned, not
  implemented** multi-engine assurance benchmark protocol: paired native-versus-framework
  comparisons, separate quality/governance/portability/effort/operations metric families, a
  deterministic assurance scenario corpus, and reproducibility requirements. Lot 22's scope and
  acceptance evidence, and `docs/refactoring-plan.md`, now point to it.
- **Known limitations:** the script has no unit test yet; it does not detect two article titles
  that normalize to the same slug (the second paragraph would be dropped while its questions still
  reference the first); its output records no source checksum or licence, which the planned
  protocol requires for imported snapshots; and most datasets named in the protocol are not yet
  backed by the research digests.

### Added — engine-independent assurance contract and conformance report (Lot 21, 2026-09-10)

- `contracts/assurance.py` (new): `AssuranceLevel` (`L0`/`L1`/`L2`, matching
  [ADR-0015](docs/adr/0015-portable-assurance-and-external-application-boundary.md) §3's table),
  `EvidenceStatus` (`unsupported`/`observed`/`verified`/`enforced`), an eight-kind `EvidenceKind`
  catalog (identity/tenant, retrieval provenance, egress decision, policy decision, audit
  completion, usage/cost, feedback/review routing, streaming prevalidation), and
  `ConformanceReport` — `achieved_level` is a **computed property**, not a constructor field, so
  no adapter can assert its own level.
- `DocumentEngine.conformance_report(context) -> ConformanceReport` (new, additive method).
  Implemented truthfully by both shipped adapters — `RAGEngine.conformance_report()` (native) and
  `LangGraphEngineAdapter.conformance_report()` — from two separate sources: control-surface
  evidence, where a wired role counts only if it also satisfies its contract Protocol (a plain
  object registered as a tenant policy earns nothing), and execution evidence recorded while
  actually serving that request. `RETRIEVAL_PROVENANCE` is earned only when the framework's own
  grounding check (`classify_provenance()`) confirms every returned citation against the chunk it
  names — the passage really appears in that chunk's text, and the page and source match —
  `Generator` requires nothing about citations, so a generator returning none, unrelated ones, or
  a fabricated passage on a genuinely retrieved chunk id never yields a provenance claim. A report
  for a request that has not executed cannot exceed L0, and a reused request id never inherits an
  earlier attempt's evidence.
- LangGraph's own documented scope boundary (it never emits `RAGEngine`'s audit events) now shows
  up as a concrete, honest `AUDIT_COMPLETION: unsupported` in its report — capping it below `L2`
  even when tenant isolation, guard, and egress are all wired, rather than manufacturing
  native-equivalent parity it cannot back.
- New optional manifest field `assurance.min_level` — a manifest requiring an unmeetable minimum
  level fails before any request is served. Because a startup gate has no execution evidence, it
  is checked against a *capability* profile: advisory at `mrag validate` time (nothing is
  constructed there) and authoritatively at the end of `wire()`, against the components actually
  built and their Protocol conformance. That gate promises only that the required controls are
  **declared, wired and structurally conformant** — Protocol membership cannot prove enforcement,
  so a structurally valid no-op control passes it. Recorded as an accepted risk in
  [ADR-0017 §9](docs/adr/0017-engine-independent-assurance-contract.md); enforcement is certified
  behaviourally by the conformance harness instead, and operators wiring third-party controls at
  `l2` must run it against them.
- `tests/contract/test_engine_conformance.py` gained one reusable, **status-aware** harness run
  against the fake *and* both real shipped adapters: for every evidence kind a report claims above
  `unsupported`, the suite must own a behavioural probe *at the claimed strength* and that probe —
  plus every weaker one — must pass, so neither a claim nothing verifies nor a claim promoted up
  the ladder without evidence can survive. `enforced` requires a denied or failing control to
  actually stop the request (a failing audit sink or review queue must fail it); `verified`
  requires the framework to reject fabricated evidence. Deliberately overclaiming, weakly probed
  and fabricating engines are fed through that same harness as negative inputs.
- [ADR-0017](docs/adr/0017-engine-independent-assurance-contract.md) — Accepted 2026-09-10 — is
  the contract ADR for this work, per [ADR-0015](docs/adr/0015-portable-assurance-and-external-application-boundary.md)
  §4's own requirement that one exist before implementation, not after.
- **Not delivered in this pass**: no on-disk exported "golden" report fixture (determinism proven
  by direct test assertions instead); the multi-engine quality/portability benchmark
  (`docs/guides/offline-evaluation.md`) remains unimplemented Lot 22 planning content this lot's
  evidence feeds, not delivers; wrapping an arbitrary existing client application is still Lot 22,
  not this lot.

### Added — data classification and provider-egress control (Lot 20, 2026-09-08)

- `Document.classification`/`Chunk.classification` (`core.enums.DataClassification`), propagated
  by every registered chunker — explicit, caller-supplied only, not inferred from content.
- `contracts/egress.py` (`EgressPolicy`, `EgressDecision`, `EgressOperation`) and
  `security.policies.egress_policy.ManifestEgressPolicy`: a fail-closed, classification-aware
  gate checked before `Embedder.embed()` (document/chunk ingestion, and query-time embedding at
  retrieval), `Reranker.rerank()`, and `Generator.generate()`, on both the native engine and the
  LangGraph delegated-engine handoff. A `local: true` provider is always allowed; an unknown
  provider or unclassified content with no explicit manifest permission is denied by default.
- New manifest section `governance.egress_policy` — optional for a purely local pipeline (absent
  = unchanged pre-Lot-20 behavior, same optionality as `tenant_policy`/`redactor`), but
  **mandatory the moment a manifest wires one of this framework's own known remote provider
  types** (`openai`, `anthropic`, `openai-embeddings`): such a manifest fails at `wire()`, before
  any request reaches the runtime deny-by-default path, unless `governance.egress_policy` covers
  that provider explicitly (even to declare it fully allowed). All three shipped presets
  (`local-hybrid-rag.yaml`, `secure-enterprise-rag.yaml`, `langgraph-rag.yaml`) now configure it,
  with `max_classification: restricted` to preserve their exact prior behavior — no real
  classification data flows through any of them today.
- New typed `EgressDeniedError` (`SecurityError` subclass) — maps to HTTP 403 / CLI exit 3
  automatically. Content-free `AuditEventType.EGRESS_DECISION` evidence — for both allowed and
  denied decisions — and `mrag.egress.{allowed,denied}` counters.
- `Chunk.classification` round-trips through both Qdrant adapters (dense and sparse): persisted
  on `index()`, reconstructed on retrieval.
- Codex review pass 1 found this and 3 other real issues (`CHANGES_REQUIRED`); corrected in the
  same pass — see `docs/refactoring/lot-20-data-classification-egress-control.md` §8. Two
  findings needed a decision beyond an implementation pass's own authorization: the fail-closed
  default described above was decided the same day, after an initial "keep opt-in, accept the
  risk" answer was revisited; [ADR-0016](docs/adr/0016-provider-egress-control.md) drafted for
  the outbound-data boundary and **Accepted 2026-09-09**.
- **Not delivered**: no pseudonymization/reversible token mapping; provider profiles model only
  `{local, max_classification}`, not retention/residency/DPA terms; the fail-closed default
  covers only this framework's three known built-in remote provider types, not arbitrary
  third-party or future adapters — a deliberate, ADR-recorded scope boundary, not an oversight.
  See `docs/refactoring/lot-20-data-classification-egress-control.md` for full evidence and the
  reasoning behind each scope decision.

### Fixed — container-build supply-chain hardening (2026-09-03)

- CPU-only PyTorch resolves consistently across every install path (CI jobs, the Dockerfile's
  runtime stage, and the license/SBOM job's dedicated venv) via
  `--extra-index-url https://download.pytorch.org/whl/cpu`; `pip-audit` instead runs with
  `--disable-pip` against the fully pinned, hashed lock, avoiding a hash-checking-mode conflict
  the extra index URL caused for `markupsafe`.
- `scripts/run_benchmark.py`'s golden-set loader derives deterministic UUID5 ids for corpus
  chunks instead of passing raw YAML slugs — Qdrant only accepts unsigned-int or UUID point ids.
- Fixed a stale `HybridRetriever._bm25` attribute reference (renamed to `_lexical` at Lot 5) and
  redirected `structlog`'s default stdout logger to stderr in the deterministic e2e replay script,
  which was corrupting the JSON contract the subprocess writes to stdout.
- `python:3.12-slim` base image digest refreshed to pick up Debian's `openssl`/`libssl3t64`
  security update; Grype's vulnerability gate now prints its findings as a readable table in the
  job log (previously SARIF-only, invisible outside the Security tab). Added `.grype.yaml`: a
  `fix-state: wont-fix` rule accepts CVEs Debian has explicitly declined to backport (no image
  refresh or dependency change can resolve those), plus three individually-reviewed entries for
  Python-interpreter CVEs fixed only on 3.13+/3.14+/3.15+ lines this project doesn't yet target.
- Removed the Grype SARIF upload step: GitHub Advanced Security / Code scanning is unavailable for
  a private, personal-account repository regardless of plan, so the step could never succeed here.
- Accepted `psycopg`/`psycopg-binary`/`psycopg-pool` (LGPL-3.0-only) in `.claude/license-baseline.txt`
  — same unmodified-dependency reasoning already applied to `chardet`.

### Documentation — product and implementation alignment (2026-09-02)

- Reframed the project as a portable Document AI assurance framework with a native reference RAG
  engine, designed to complement external orchestration frameworks and cloud services rather than
  replace them.
- Accepted ADR-0015 for framework-built and bring-your-own-application adoption through explicit
  L0/L1/L2 assurance levels. No planned contract is presented as shipped.
- Added planned Lots 21–22 for an engine-independent assurance contract and external-application
  adapters/conformance, explicitly sequenced after Lot 20 provider-egress protection and ADR
  approval.
- Reconciled README, roadmap, business case, architecture, onboarding, API, manifest, deployment,
  security, evaluation, glossary, and internal AI-development guidance with the current source.
- Documented shipped feedback, human review, drift detection, NDCG/golden-set evaluation and the
  `/feedback` API, while narrowing LangGraph claims to its implemented control subset.
- Made the current data-protection boundary explicit: classification-aware, deny-by-default
  provider egress is planned, and deployments need external controls or approved local providers
  until it ships.

### Added — operational hardening and observability (through 2026-08-26)

- Bounded `/ready` dependency probes for Qdrant, PostgreSQL and configured LLM generators
  ([ADR-0010](docs/adr/0010-health-checkable-and-readiness-semantics.md)).
- Durable PostgreSQL lifecycle/audit adapters, packaged migrations, reconciliation and retention
  administration commands ([ADR-0011](docs/adr/0011-postgresql-migrations-pooling-and-retention.md)).
- OpenTelemetry-compatible distributed tracing through optional `Tracer`/`Span` manifest roles
  ([ADR-0012](docs/adr/0012-opentelemetry-tracing-port.md)).
- Operational `Meter` counters, histograms and gauges, static generation-cost estimates, and
  reference dashboard/alerts/SLO/runbooks ([ADR-0013](docs/adr/0013-operational-metrics-meter-port.md)).
  No shipped preset enables the tracer or meter yet; both require a custom manifest.
- Contextual ingestion enrichment: chunks retain original citation content while using a
  title-prefixed `embedding_text` for embedding.
- Main CI coverage for live Qdrant/PostgreSQL integration, deterministic governed e2e and Compose
  smoke; real-LLM e2e remains in the scheduled/manual nightly workflow.

### Documentation — implementation alignment (2026-08-26)

- Reconciled active architecture, onboarding, manifests, examples and operations documentation
  against the current source tree and test/CI entry points.
- Marked the current LangGraph graph as fixed rather than multi-agent, the `hybrid_search` example
  as presently incompatible, and the readiness/review metric sampling limitations explicitly.

### Fixed — embedder/Qdrant vector-dimension consistency (2026-08-11)

[ADR-0009](docs/adr/0009-vector-indexer-dimension-reconciliation.md): `QdrantStore` no longer
defaults silently to a 384-dimensional collection regardless of the wired embedder's real output
size. `secure-enterprise-rag.yaml` and `langgraph-rag.yaml` (both `bge-base-en-v1.5`, 768-dim)
were previously exposed to this — a fresh deployment of either would have created an
incompatible 384-dim collection. Vector size is now derived from the wired `Embedder` when
`indexer.config.vector_size` is left unset, and validated with a clear `ConfigurationError`
before any collection is created or used when it is set explicitly and disagrees.

- **BREAKING for existing `langgraph-rag.yaml` deployments**: its collection name changed from
  `documents` to `langgraph_documents`, to stop colliding with `local-hybrid-rag.yaml`'s
  same-named, 384-dim collection on the same default `localhost:6333`. Existing data under
  `documents` is not deleted, just no longer queried by this preset. Before upgrading a live
  deployment: reingest into `langgraph_documents`, or copy the physical collection via
  `create_snapshot()`/`recover_snapshot()` into a real `langgraph_documents` collection. A
  Qdrant collection *alias* is not a working substitute: `QdrantStore._ensure_collection()` only
  recognizes physical collections, not aliases, so it would try to create a colliding physical
  collection under the alias's name instead of using it. See the migration note in
  `manifests/presets/langgraph-rag.yaml` for exact commands.
- New `VectorIndexer(Indexer, Protocol)` sub-protocol (`contracts/indexing.py`) — opt-in, so
  non-vector `Indexer` implementations are unaffected.

### Refactoring programme — engine-agnostic control plane (2026-08-04 to 2026-08-05)

Full 18-lot refactoring programme (`docs/refactoring-plan.md`), accepting
[ADR-0005](docs/adr/0005-document-ai-control-plane-boundary.md)'s product-boundary pivot: this
package owns governance, audit, evaluation, config/manifests, tenant isolation, and portability
natively, and delegates generic multi-agent orchestration and GraphRAG traversal to a selected
external engine (LangGraph, [ADR-0006](docs/adr/0006-external-engine-selection.md)) via an
adapter behind a vendor-neutral `DocumentEngine` port. Engineering work across all 18 lots is
complete; final sign-off (architecture/security/operations/legal/business-quality) is reserved
for Herbert Gourout per `docs/refactoring/lot-0-baseline.md`'s sole decision authority — not
claimed here. Full evidence trail: `docs/refactoring/lot-{0..18}-*.md`, one file per lot.

**Phase A — Control and evidence (Lots 0-5):** baseline/ownership recorded; ADR-0005 accepted;
Claude/repository instructions realigned; reproducible `.venv` + CI (compilation, layering,
mypy baseline, wheel build, clean-install smoke test); characterization tests for every public
surface (found and fixed a routing bug that made `POST /answer` always return 422); corrected
unsupported delivered/security/compliance claims across README/docs.

**Phase B — Architecture foundations (Lots 6-10):** LangGraph selected via a real spike against
LlamaIndex Workflows (ADR-0006); `contracts/engine.py`'s `DocumentEngine` port (vendor-neutral
types, semantic conformance suite); `NativeEngineAdapter` (empty capability set, honest not
aspirational); strict versioned manifests with `${VAR}`/`secret://` resolution; trace/audit
schema foundation (`AuditEvent`, `AuditSink`, PII/secret payload allowlist).

**Phase C — Enterprise correctness (Lots 11a-14):** threat model + data-classification policy;
fail-closed tenant isolation (`TenantIsolationPolicy`, real Keycloak `TokenVerifier`); redaction
+ per-decision audit events + human-review gate; document lifecycle (identity, idempotency,
delete — closing a "no `delete()` at all" gap); index reconciliation and schema versioning
(found and fixed `QdrantStore` silently dropping `tenant_id`); backup/restore/erasure with a
genuine executed round-trip; corrected `Metrics` vocabulary and `BenchmarkRunner`'s
failure-masking; timeouts, retry/circuit-breaker primitives, and thread-safety locks on every
in-memory reference store with a genuine read-then-write race.

**Phase D — Portability and delivery (Lots 15-18):** `LangGraphEngineAdapter`, the second
`DocumentEngine` implementation, validated against a real, structurally different engine (found
and fixed a hexagonal-layering violation and two separate governance-parity bugs — one in Lot
15 itself, a second found only by Lot 18's pilot script); API authentication/rate-limiting/
typed-safe-errors and CLI exit codes (found and fixed `RAGEngine.retrieve()` silently bypassing
tenant isolation); single version source, dependency licence gate, SBOM, and an immutable
container build (two licence/legal findings — `pymupdf`'s AGPL dual licence, the 56 research
PDFs' unverified redistribution rights — escalated and explicitly left as accepted risk, not
resolved unilaterally); deployment/backup/restore/rollback runbooks (found and corrected that
`app/settings.py`'s entire `Settings` class is never actually wired into the pipeline-loading
path); removal of an entire dead agent/routing/planning prototype cluster with zero test
coverage and zero consumers, superseded by ADR-0005's delegation decision; a real
native-vs-external-engine pilot comparison that found and fixed a real CI gap (`langgraph` never
installed in the `test-unit`/`coverage` jobs).

### Stabilization — layer boundaries and control-plane activation (completed 2026-08-07)

[ADR-0007](docs/adr/0007-layer-boundaries-and-control-plane-activation.md), accepted: closes the
gap between the published dependency direction and the real one, and between the manifest V2
schema's declared governance sections and what actually activates. Full evidence:
`docs/architecture/capability-matrix.md`.

- **Layering**: moved `Container` to `orchestration/container.py` (was `app/container.py` —
  orchestration importing from app was backwards); moved the concrete component-composition
  function to `app/default_factories.py`; added `app/public.py`/`app/application.py` as the only
  facade `api/`/`cli/` may import. `scripts/check_layering.py` now enforces the full
  core→contracts→domain→adapters→orchestration→app→api/cli table with a `--strict` CI gate and
  its own test suite (`tests/unit/scripts/test_check_layering.py`).
- **Manifest V2 activation**: `GovernanceSection.tenant_enforcement` is now an explicit,
  validated intent flag (`true` without a `tenant_policy` component fails validation, not a
  silent no-op). `PostgresAuditSink`/`PostgresLifecycleLedger` are now manifest-activatable, not
  Python-injectable only. Added `tests/contract/test_telemetry_conformance.py` (previously
  zero conformance coverage for the `Telemetry` Protocol).
- **Manifests split into `presets/` (Runnable) and `blueprints/` (design sketches, never
  loaded)**: converted `secure-enterprise-rag.yaml` into a real V2 manifest (governance, quality
  gate, `${VAR}`/`secret://` resolution — was a broken placeholder referencing nonexistent
  policy files); renamed `agentic-rag.yaml` → `langgraph-rag.yaml` with
  `engine.adapter: langgraph` replacing the never-built native five-agent design; moved
  `graph-memory-rag.yaml`/`multimodal-rag.yaml` to `manifests/blueprints/`, stripped of their
  fictional native `agents:`/`graph_store:` blocks.
- **Removed dead code with zero consumers** (restorable via git history): `app/settings.py`'s
  orphaned `Settings` class; `memory/graph/` entirely (`KnowledgeGraph.neighbours()`/
  `subgraph_for_query()` were genuine GraphRAG traversal, not passive storage — resolves
  ADR-0007's open decision on this); `AgentError`/`GraphError`; `Trace.routing_strategy` (bumps
  `TRACE_SCHEMA_VERSION` to 1.2); the unused `planner`/`graph_store` registry roles;
  `RetrievalMethod.GRAPH`/`.MULTIMODAL` and the fully-unused `ChunkingStrategy` enum.
- **Finalization**: API and CLI now honor `engine.adapter` through `load_application()`;
  document identity hashing lives in `core/`; application, API lifespan, and CLI commands close
  wired resources deterministically. Local gates pass with 588 unit/contract tests; live
  Qdrant/PostgreSQL/LLM validation remains a CI/staging sign-off because those services and
  credentials are not available in the local environment.

### Added — 2026-07-12 (`feature/v1-sota-alignment`)
- `Parser` Protocol (`contracts/parsing.py`) + DOCX and HTML parsers; PDF parsing switched from pypdf to pymupdf.
- Weighted Reciprocal Rank Fusion (`weights` parameter, defaults reproduce unweighted RRF); `HybridRetriever` passes manifest weights through.
- `examples/hybrid_search/`: retrieval-only demo comparing vector-only / BM25-only / RRF-fused results (no LLM key required).
- Research digests (`docs/research/DIGEST-*.md`): 39 arXiv papers distilled into 7 actionable domain digests, wired into 8 Claude Code skills and CLAUDE.md coding rule 8 ("state of the art first").
- Test coverage: CrossEncoderReranker (unit + contract), both generators, citations builder, lexical gate, parsers — 124 → 191 tests.
- `docs/guides/code-walkthrough.md`: progressive reading guide to navigate the codebase.

### Changed — 2026-07-12 (state-of-the-art alignment)
- Chunkers now size in **tokens** (pluggable counter; whitespace default, tiktoken opt-in) with defaults 512/128 (25% overlap, arXiv:2604.12047); `AdaptiveChunker` merges fragments < 100 tokens (arXiv:2603.25333).
- `BasicSecurityGuard`: 5 → 12 injection patterns across 3 documented families (arXiv:2505.06579, 2604.12201); `check_answer` implemented — blocks answers containing URLs absent from citations (corpus-poisoning marker).
- Generator system prompts add a negative-rejection clause ("say you don't know", arXiv:2404.10981 §7.1); citation passages truncate at sentence boundaries (arXiv:2506.10408).
- `GroundednessValidator` reframed as a lexical-support gate (not a faithfulness metric); unsourced constants (`rrf_k=60`, 0.7/0.3 fusion weights, `temperature=0.1`) documented as engineering priors to tune on the V1.1 golden set.
- Lint debt cleared: `scripts/check.sh full` now passes (47 pre-existing ruff errors fixed).

### Added
- Full `src/modular_rag/` implementation: contracts, core models, orchestration engine, ingestion pipeline, hybrid retrieval (vector + BM25 + RRF), cross-encoder reranker, OpenAI and Anthropic generators, basic security guard, PII redactor, evaluation scorers, multi-agent stubs (coordinator, extractor, synthesizer, validator), knowledge graph (networkx), EvoRAG graph versioning, CLI (`mrag ask`, `mrag ingest`), FastAPI REST endpoint.
- Five populated YAML manifest presets: `local-hybrid-rag`, `secure-enterprise-rag`, `agentic-rag`, `graph-memory-rag`, `multimodal-rag`.
- Three Architecture Decision Records: ADR-0001 (modular architecture), ADR-0002 (contracts + plugins), ADR-0003 (security + governance).
- `docs/architecture/overview.md`: full technical specification V1→V5.
- `docs/architecture/module-model.md`: layer boundaries.
- `docs/architecture/runtime-flow.md`: sequence and flow diagrams.
- `docs/architecture/security.md`: attack surfaces and guard chain.
- `ROADMAP.md`: V1→V5 milestones with checkboxes.
- `CONTRIBUTING.md`: setup, rules, step-by-step guide to add a component.
- `CLAUDE.md`: guidance for Claude Code sessions.
- `pyproject.toml`: full dependency groups (v1, v3, v4, v5, dev).

### Changed
- `README.md`: refactored to declare pre-alpha status, add "Why this framework?" section, target API snippets, Apache 2.0 licence.

## [0.0.1] — 2026-05-20

### Added
- Initial project scaffold: directory tree, empty modules, manifests, docs, ADR, `.gitlab/` templates.
- `README.md` (initial version).
