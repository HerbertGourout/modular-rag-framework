# Documentation Alignment & Consistency Audit

> **Historical snapshot.** This report records the repository state on 2026-08-12 and is retained
> as audit evidence. For current capability status, use
> [`architecture/capability-matrix.md`](architecture/capability-matrix.md), the current roadmap,
> and the executable validation commands documented there.

**Date:** 2026-08-12  
**Scope:** active Markdown documentation at the repository root, `docs/`, `manifests/`,
`examples/`, and module-level `CLAUDE.md` files; implementation and configuration under
`src/`, `tests/`, `manifests/`, `scripts/`, `docker/`, `pyproject.toml`, and GitHub Actions used
as verification evidence.  
**Authority order:** accepted ADRs and executable code, then `ROADMAP.md` and
`docs/architecture/capability-matrix.md`. Historical records under `docs/archive/` and
`docs/refactoring/` were classified as snapshots rather than silently rewritten.

## Executive summary

The active documentation is now broadly aligned with the implementation and ADR-0005 through
ADR-0009. The largest pre-audit risk was not broken links: it was contradictory maturity
language. Several high-visibility pages simultaneously described V1 as complete while the
roadmap correctly recorded pending V1.0 live validation and incomplete V1.1/V1.2 deliverables.
Other confirmed drift concerned nonexistent evaluation APIs/paths, overstated trace coverage,
incomplete integration prerequisites, and an unsupported fully offline/local-LLM claim.

This audit corrected those claims without changing implementation or ADR content. The active
documentation now consistently states:

- V1.0 implementation is complete and unit/contract-tested; current live Qdrant/LLM evidence is
  still pending.
- V1.1 and V1.2 are partially built. No populated golden-set catalogue, NDCG scorer, regression
  dashboard, end-to-end lineage tracker, or formatted compliance-report generator ships today.
- Evaluation and gold-dependent quality gates are programmatic offline capabilities (ADR-0008),
  not online manifest components.
- Trace coverage is real but not universal: query guard, retrieval, optional reranking, and
  generation are traced; several governance/redaction/review decisions lack their own step.
- The complete integration directory needs Qdrant and PostgreSQL; E2E prerequisites are
  scenario-dependent, while the official aggregate gate intentionally requires all of them.
- A fully offline semantic deployment needs a local-LLM generator adapter that is not currently
  shipped.

## Method

Each active document was classified by purpose, then checked against the corresponding source:

| Documentation subject | Verification source |
|---|---|
| Contracts and public signatures | `src/modular_rag/contracts/`, public facade, contract tests |
| Built-in component names | `src/modular_rag/app/default_factories.py` |
| Manifest fields and activation | `contracts/manifests.py`, `config_resolution.py`, `registry.py`, presets |
| Runtime order and controls | native/LangGraph engines, `ApplicationService`, API and CLI |
| Test/CI claims | test tree, pytest markers, `scripts/check.*`, `.github/workflows/ci.yml` |
| Packaging/dependencies | `pyproject.toml`, Docker entry point |
| Current/future status | accepted ADRs, `ROADMAP.md`, capability matrix |
| Links and retired APIs | `scripts/check_docs.py`, repository-wide path/symbol searches |

No claim was upgraded from planned to implemented solely because a class or manifest field
exists; it also had to have a reachable, tested consumption path.

## Documents conforming after the audit

### Primary entry points

- `README.md`: aligned after corrections to component activation, integration prerequisites,
  evaluation scope, trace coverage, and maturity language.
- `ROADMAP.md`: authoritative and explicit about V1.0 pending live evidence, partial V1.1/V1.2,
  and delegated future capabilities.
- `CONTRIBUTING.md`: commands, paths, registration sequence, tests, and service prerequisites
  align after the integration-prerequisite correction.
- `CHANGELOG.md`: retained as a chronological release record; statements about removed code are
  historical, not current capability guidance.

### Architecture and API

- `docs/architecture/capability-matrix.md`: strongest concise source for operational,
  programmatic, delegated, blueprint, and unresolved states.
- `data-model.md`, `module-model.md`, `runtime-flow.md`, `security.md`, `threat-model.md`,
  `data-classification-policy.md`, and `document-engine-contract.md`: aligned with the current
  code and ADR boundaries.
- `overview.md`, `structure.md`, `_index.md`, and `glossary.md`: aligned after correcting stale
  evaluator paths, maturity wording, and trace-coverage generalizations.
- `docs/api/rest.md` and `docs/api/_index.md`: accurately describe startup fail-closed identity,
  routes, typed errors, rate limiting, and the deliberately shallow `/ready` probe.

### Runtime, manifests, examples, and operations

- `manifests/README.md` and `manifests/_index.md`: correctly separate runnable presets from
  non-loadable blueprints and describe native versus delegated activation.
- Environment/schema indexes: correctly identify future environment overlays and generated
  schema material.
- `getting-started.md`, `installation.md`, `deployment.md`, `observability.md`,
  `troubleshooting.md`, and `backup-restore.md`: operationally aligned after removing the load
  test's implied production-readiness conclusion.
- `examples/simple_qa/README.md` and `examples/hybrid_search/README.md`: commands and manifest
  relationships align with current entry points.

### Project tooling documentation

- `AGENTS.md`, `docs/guides/ai-engineering-workflow.md`, `model-routing.md`, and
  `claude-code.md`: aligned with the one-writer/independent-reviewer workflow.
- The two long Claude Code guides remain intentionally illustrative, but repository-specific
  examples now point to real retriever, evaluation, redaction, agent, and MCP paths rather than
  nonexistent APIs.

### Immutable or non-operational sources

- Accepted ADRs were verified as the decision authority and not modified.
- `docs/archive/` and `docs/refactoring/` remain point-in-time historical evidence. They may name
  retired APIs by design and are clearly separated from active guidance.
- `docs/research/` records evidence and design context; it does not assert runtime activation.

## Documents updated

| Document | Priority | Confirmed reason | Applied correction |
|---|---|---|---|
| `CLAUDE.md` | Critical | Encoded nonexistent V1.1 APIs, complete V1 claims, GDPR-ready audit, universal tracing, and incomplete integration prerequisites | Replaced with current evaluator/audit inventory, partial status, exact trace gaps, and real service matrix |
| `README.md` | Critical | Overstated manifest activation and trace coverage; integration omitted PostgreSQL; stray export artifact | Scoped activation, documented ADR-0008 exception and trace gaps, corrected commands/status, removed artifact |
| `docs/architecture/_index.md` | High | Said V1 was proven end-to-end | Aligned with V1.0 pending live evidence and partial V1.1/V1.2 |
| `docs/architecture/overview.md` | High | Referenced nonexistent `eval/metrics/` and `eval/benchmark_runner.py` | Pointed to `eval/scorers/` and `eval/runners/benchmark.py` |
| `docs/architecture/structure.md` | High | Restated universal observability as an invariant | Linked the rule to actual partial coverage |
| `docs/guides/framework-overview-onboarding.md` | Critical | Repeated V1-complete, universal tracing, turnkey-production, and fully offline/local-LLM claims | Added precise maturity, trace, production-qualification, and local-generator gaps |
| `docs/guides/validation-protocol.md` | High | Claimed V1 complete and treated integration as Qdrant-only | Corrected status, Qdrant/PostgreSQL matrix, and component registration sequence |
| `CONTRIBUTING.md` | Medium | Integration command described Qdrant as its only service | Documented full-directory PostgreSQL requirement |
| `docs/business-case.md` | High | Promised fully on-premise operation despite no local semantic generator; overstated trace coverage | Scoped on-premise capabilities and named the missing adapter |
| `docs/glossary.md` | Medium | Conflated execution trace with audit record and claimed every step was traced | Distinguished `Trace` from `AuditEvent` and listed actual coverage |
| `docs/onboarding.md` | High | Declared V1 end-to-end complete despite pending live evidence | Scoped status to implementation and tests |
| `docs/guides/backup-restore.md` | Medium | One load test was presented as sufficient production evidence | Reframed it as one qualification input |
| `docs/guides/claude-code-complete-development-guide.md` | High | Contained nonexistent retriever, evaluator, redaction contracts, paths, result types, and manifest schema | Replaced with the real protocols, paths, tests, and activation model |
| `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md` | Medium | Used production-ready wording and stale example paths/prerequisites | Scoped document/framework maturity and corrected examples |
| `docs/guides/adoption-metrics.md` | Medium | Named a nonexistent validation script while understating the real layering checker | Pointed to `check_layering.py` and separated manual checks |
| `docs/guides/claude-code-advanced-config.md` | Low | Presented a nonexistent project agent as if checked in | Marked it illustrative and named the real reviewer |
| `docs/guides/claude-code-mcp-setup.md` | Low | Referenced nonexistent `.claude/CLAUDE.md` | Pointed to root `CLAUDE.md` |

## Inconsistencies found

### Documentation versus code

- Nonexistent `MetricsProtocol`/`MetricProtocol`, `eval/metrics/`, `eval/golden_sets/`, and
  regression-dashboard APIs were described as current extension points.
- Generic examples used a nonexistent BM25 adapter/config and returned `Document` objects,
  contradicting the real `Retriever` contract (`Query` to `RetrievedChunk`).
- A nonexistent PII detector protocol/registry and manifest schema were shown despite the real
  single `PatternRedactor` implementation already handling Luhn-validated cards.
- PostgreSQL integration tests were omitted from several prerequisite summaries.
- Several pages claimed full trace coverage that the engine does not provide.
- Fully offline inference was claimed despite only OpenAI/Anthropic semantic generators being
  registered; the deterministic generator exists for tests, not semantic production answers.

### Documentation versus ADRs

- Manifest-first language incorrectly included gold-dependent evaluation helpers, contrary to
  ADR-0008's offline boundary.
- Some summaries blurred native owned control-plane functions with delegated orchestration,
  despite ADR-0005/0006. Detailed architecture pages were already correct; summaries were fixed.
- Vector dimension guidance was checked against ADR-0009 and is aligned: Qdrant derives or
  validates dimensions lazily before first collection use.

### Documentation versus roadmap

- V1-complete wording contradicted the authoritative V1.0 pending live validation and partial
  V1.1/V1.2 sections.
- Structured audit primitives were occasionally marketed as GDPR-ready despite missing lineage,
  report generation, retention enforcement, and production evidence.

## Remaining limitations and recommendations

### Remaining limitations

1. `examples/simple_qa/main.py` contains an obsolete environment-variable name in its module
   docstring. It is documentation embedded in a Python implementation file and was not changed
   because this audit was explicitly forbidden from modifying code; the adjacent README is
   correct.
2. Service-backed integration/E2E behavior cannot be certified by documentation inspection.
   Those suites are not run in CI and require real Qdrant/PostgreSQL and, for the LLM scenario,
   an external key. **Superseded 2026-08-21**: this limitation was accurate as of this audit's
   2026-08-12 date but no longer holds — Batch 10 (an external plan, pushed after this audit)
   wired `tests/integration/` and the deterministic e2e scenario into `.github/workflows/ci.yml`
   against real Qdrant/PostgreSQL service containers, and the LLM-backed scenario into a separate
   scheduled/manual `nightly.yml`. Left as originally written above (not rewritten) so this
   remains an honest record of what was true on this audit's own date; see `README.md`/`CLAUDE.md`
   for the current state.
3. Claude Code product-reference pages describe a fast-moving external tool. This audit checked
   their repository paths and internal consistency, not every upstream product setting against
   external vendor documentation.
4. Historical records deliberately contain retired names. They must remain visibly classified
   as historical so search results are not mistaken for active guidance.

### Professional documentation recommendations

1. Make the capability matrix machine-adjacent: generate its built-in component table from
   `create_default_registry()` and its manifest fields from Pydantic JSON Schema.
2. Extend `scripts/check_docs.py` with checks for documented Python module paths and a small
   ratchet of prohibited maturity phrases outside roadmap/history files.
3. Publish a versioned documentation site with explicit **Current**, **Preview**, **Delegated**,
   and **Historical** badges. Keep tutorials, how-to guides, reference, and explanation separated
   (Diátaxis-style navigation).
4. Add executable documentation tests for CLI commands, manifest snippets, API request bodies,
   and import examples. Broken prose examples are more damaging than broken links.
5. Provision Qdrant/PostgreSQL service containers in a dedicated CI job and run the deterministic
   secure E2E scenario without an LLM key. Keep the paid LLM scenario as an explicit release gate.
6. Add component-reference pages generated from Protocol signatures and registered factories,
   including configuration fields, optional dependencies, lifecycle behavior, and examples.
7. Define release vocabulary centrally (`implemented`, `unit-tested`, `integration-validated`,
   `production-qualified`) and prohibit unqualified uses of `complete`, `shipped`, and
   `production-ready` in active documentation.
8. Add a concise operations matrix covering single-process limitations (BM25 memory, rate-limit
   scope), dependency health probes, scaling model, secret sources, backup evidence, and SLO
   ownership before presenting the framework as deployable infrastructure.

## Validation results

- Documentation checker: passed across 163 Markdown files.
- Relative links and blueprint/preset classification: passed.
- Repository Python-module reference scan: no unresolved active reference remained except
  explicitly marked hypothetical extension files.
- `git diff --check`: passed.
- No implementation file or ADR was changed by this documentation audit.
