# Changelog

All notable changes are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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
