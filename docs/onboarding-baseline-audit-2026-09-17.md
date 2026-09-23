# Onboarding Baseline and Documentation Truth Map

- **Date:** 2026-09-17 (revised the same day after Codex review pass 1)
- **Batch:** [`docs/onboarding-overhaul-plan.md`](onboarding-overhaul-plan.md) — Batch 0
- **Immutable base:** `2150ce266da4b1e6b52dda9e8152ee97ec7d8cb4` (`main`)

**Scope:** onboarding, architecture, development, testing, operations, Claude Code, Codex,
review, troubleshooting, and contribution documentation.

Implementation, tests, manifests, and CI workflows under `src/`, `tests/`, `manifests/`,
`scripts/`, and `.github/workflows/` were read only as verification evidence — none were
modified.

**Authority order:**

1. executable code, manifests, tests, CI, accepted ADRs and public contracts,
2. then `CLAUDE.md`/`AGENTS.md`/path-scoped rules,
3. then `ROADMAP.md`/`docs/refactoring-plan.md`,
4. then guides and indexes,
5. then Git history — per this plan's §4.

**Predecessor:** [`docs/documentation-alignment-audit-2026-08-12.md`](documentation-alignment-audit-2026-08-12.md),
a comparable audit already self-marked as a historical snapshot.

Its findings predate Lots 20–22 and the current Claude Code guide set; this document supersedes
it as the current baseline.

## Contents

1. [Executive summary](#1-executive-summary)
2. [Controlled vocabulary for capability states](#2-controlled-vocabulary-for-capability-states)
3. [Document inventory and canonical status](#3-document-inventory-and-canonical-status)
4. [Verified incorrect documentation](#4-verified-incorrect-documentation)
5. [Missing operational knowledge](#5-missing-operational-knowledge)
6. [Capability status verified against code](#6-capability-status-verified-against-code)
7. [Acceptance criteria for this batch](#7-acceptance-criteria-for-this-batch)
8. [Recommendations by batch](#8-recommendations-by-batch)
9. [This batch's own status](#9-this-batchs-own-status)

---

## 1. Executive summary

This baseline covers every in-scope documentation cluster member by member (§3).

Its central result is that **status drift is concentrated in secondary documents that a newcomer
is still routed to**, not in the primary status sources. `CLAUDE.md`, `ROADMAP.md`,
`docs/architecture/capability-matrix.md`, `docs/architecture/_index.md`, and
`docs/architecture/security.md` state Lot 20, Lot 21, and Lot 22 correctly. Several documents
linked from onboarding paths do not.

The findings, in decreasing order of onboarding impact:

1. **Shipped Lot 20/Lot 21 behaviour is still described as proposed or absent in eight places
   across five documents a newcomer is told to read** — including a guide self-titled "Complete
   Overview & Onboarding", the glossary, the business case, `docs/onboarding.md` itself, and a
   Claude Code subagent definition that instructs future agent sessions (§4.1, rows S1–S8).

2. **No single declared entry point for two subjects, and a conflicting one for a third.** A
   second framework overview competes with `docs/onboarding.md`; four Claude Code guides overlap,
   and the largest one already carries a `START HERE` declaration that contradicts the
   first-time-setup guide and contradicts itself two paragraphs later (§3.8, §4.3).

3. **The canonical delivery-workflow guide and `CLAUDE.md` disagree on the default delivery path**
   (§4.2, row C1).

4. **Factual drifts in counts and formatting**: two mutually contradictory ADR counts, a stale
   egress claim about a manifest that already enforces it, and a broken Markdown table (§4.1).

5. **A retired native multi-agent design is still presented as planned** in a Claude Code guide,
   using a manifest field that does not exist (§4.1, row S9).

6. **One operational hazard is undocumented anywhere**: approving a command at project scope
   rewrites the shared `.claude/settings.json` (§5.1).

No implementation, test, manifest, configuration, or existing guide was modified to produce this
audit.

---

## 2. Controlled vocabulary for capability states

Codex review pass 1 (HIGH-002) found that the first draft of this section put ownership and
availability on a single axis, so `delegated` could be read as "available through the selected
engine." That reading is false for every capability this repository delegates today.

The vocabulary is therefore two independent dimensions, and **a delegated capability always
carries an availability state as well**.

### 2.1 Availability — is it usable today?

**`implemented`**

- **Definition:** Shipped, reachable through a supported entry point (a manifest field, CLI
  command, or API route), and covered by a test that exercises that path.
- **Test to assign it:** Code, wiring, and a test all exist and are reachable without special
  flags.

**`partial`**

- **Definition:** A real, tested capability exists, but a materially advertised sub-scope of it
  is missing.
- **Test to assign it:** The existing scope passes the `implemented` test; the missing scope is
  named explicitly.

**`contract-only`**

- **Definition:** A `contracts/` Protocol or dataclass module exists and is exported from
  `contracts/__init__.py`, but no concrete implementation is registered in
  `app/default_factories.py` or constructed by `app/bootstrap.py`, and no manifest can select one.
- **Test to assign it:** The contract and its tests exist; no registered factory or selectable
  manifest value does.

**`planned`**

- **Definition:** Not usable today by any path in this repository, including through the selected
  external engine.
- **Test to assign it:** Nothing in `src/modular_rag/` or the shipped adapters provides it.

### 2.2 Ownership — who is meant to build it?

**`native`** — Built and owned in this repository (the default; omitted in tables).

**`delegated`** — Per an accepted ADR, deliberately **not** built natively; intended to be
provided by a selected external engine behind the `DocumentEngine` port. Says nothing about
whether that engine provides it today.

### 2.3 Composition rule

Every status is written `<availability>` or `<availability> (delegated)`. **`delegated` never
appears alone.** A reader must always be able to answer "can I use it today?" from the first word.

Example: GraphRAG traversal is `planned (delegated)` — delegation is decided, but neither this
repository nor the selected LangGraph adapter provides it.

---

## 3. Document inventory and canonical status

Every in-scope cluster is listed member by member. Where members share one purpose and status
(dated lot records, ADRs, skill definitions), they are grouped in one row that names every member.

**Status key.**

- `Canonical` — the authoritative source for its subject.
- `Reference` — accurate supporting material, not the source of truth.
- `Redirect` — intentionally forwards to another file.
- `Historical` — a dated record, correct as of its date and not expected to track current status.
- `Conflicting` — claims authority or overlaps a canonical source without a declared precedence.
- `Stale` — contains at least one verified out-of-date current-state claim (§4).

### 3.1 Primary entry points and indexes

| Document | Purpose | Status |
|---|---|---|
| [`docs/onboarding.md`](onboarding.md) | "Who reads what" map across reader profiles, plus the plain-language V1→V5 journey | **Canonical** entry point (declared by `docs/_index.md:7-11` and `CONTRIBUTING.md:12`); was **Stale** — §4.1 S5, S6, F1, all resolved by Batch 1 |
| [`docs/_index.md`](_index.md) | By-intent navigation for all of `docs/` | **Canonical** index |
| [`docs/guides/_index.md`](guides/_index.md) | By-intent navigation for `docs/guides/`, split into framework and Claude Code tooling guides | **Canonical** index for its directory; defers to `docs/_index.md` (`:65-66`) |
| [`README.md`](../README.md) | Project pitch, vision, status table | **Canonical** pitch |
| [`ROADMAP.md`](../ROADMAP.md) | Checkbox-per-feature delivery state | **Canonical** status source |
| [`CHANGELOG.md`](../CHANGELOG.md) | Dated narrative of changes | **Historical** per entry |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Git workflow, PR checklist, setup, validation, component recipe | **Canonical** contribution guide; §5.2 gap closed by Batch 7 |
| [`docs/business-case.md`](business-case.md) | Product hypothesis, target users, decision gate | **Canonical** for its subject; was **Stale** — §4.1 S4, resolved by Batch 2 |
| [`docs/glossary.md`](glossary.md) | Term definitions | **Canonical**; was **Stale** — §4.1 S2 and S3, both resolved by Batch 8 |
| [`docs/guides/framework-overview-onboarding.md`](guides/framework-overview-onboarding.md) | Business and technical overview with role-based quick starts | Precedence declared by Batch 1 (§3.8 A); was **Stale** — §4.1 S1 and S7, both resolved by Batch 2 |
| [`docs/documentation-alignment-audit-2026-08-12.md`](documentation-alignment-audit-2026-08-12.md) | Prior documentation audit | **Historical**, superseded by this document |
| [`docs/onboarding-overhaul-plan.md`](onboarding-overhaul-plan.md) | The batch plan this audit executes | **Canonical** process document |

### 3.2 Architecture

| Document | Purpose | Status |
|---|---|---|
| [`docs/architecture/_index.md`](architecture/_index.md) | Question-to-document navigation and recommended reading order | **Canonical** index; Lot 20–22 statement verified accurate (`:44-48`) |
| [`overview.md`](architecture/overview.md) | Complete technical specification: planes, roadmap, assurance phase status | **Canonical** |
| [`capability-matrix.md`](architecture/capability-matrix.md) | Capability-by-capability operational truth | **Canonical** status source at architecture level |
| [`data-model.md`](architecture/data-model.md) | Pydantic objects, fields, invariants | **Canonical** |
| [`module-model.md`](architecture/module-model.md) | Layer boundaries and forbidden-import examples | **Canonical** |
| [`runtime-flow.md`](architecture/runtime-flow.md) | Step-by-step request flow | **Canonical** |
| [`structure.md`](architecture/structure.md) | File-by-file repository map | **Canonical** (reference-depth) |
| [`security.md`](architecture/security.md) | Attack surfaces, guard chain, redaction patterns | **Canonical**; Lot 20 egress statements verified accurate (`:25`, `:84`, `:255-263`) |
| [`threat-model.md`](architecture/threat-model.md) | Assets, trust boundaries, open threats | **Canonical** |
| [`data-classification-policy.md`](architecture/data-classification-policy.md) | Classification levels, PII/tenant schema | **Canonical** |
| [`document-engine-contract.md`](architecture/document-engine-contract.md) | `DocumentEngine` compatibility and deprecation policy | **Canonical**; Lot 21 section verified (`:113`) |
| [`roadmap-mermaid.md`](architecture/roadmap-mermaid.md) | Roadmap and flows as diagrams | **Reference** (visualization of `ROADMAP.md`) |

### 3.3 Development and extension

| Document | Purpose | Status |
|---|---|---|
| [`docs/guides/getting-started.md`](guides/getting-started.md) | Clone to first query | **Canonical** first-run guide; was **Stale** — §4.1 F2 resolved by Batch 2, F3 by Batch 4 |
| [`docs/guides/installation.md`](guides/installation.md) | Python environment and extras | **Canonical**; every extras group verified against `pyproject.toml` |
| [`docs/guides/plugin-development.md`](guides/plugin-development.md) | Four-step component recipe | **Canonical** |
| [`docs/guides/code-walkthrough.md`](guides/code-walkthrough.md) | Progressive reading guide through the codebase | **Reference** |
| [`docs/guides/observability.md`](guides/observability.md) | Trace, span, and metric wiring | **Canonical** |
| [`docs/guides/offline-evaluation.md`](guides/offline-evaluation.md) | Golden-set benchmark and quality gate | **Canonical** |
| [`docs/guides/feedback-and-drift.md`](guides/feedback-and-drift.md) | Feedback, human review, drift detection | **Canonical** |
| [`docs/guides/dependency-lock.md`](guides/dependency-lock.md) | Reproducible lock update procedure | **Canonical** |
| [`docs/api/_index.md`](api/_index.md), [`docs/api/rest.md`](api/rest.md) | REST API overview and reference | **Canonical** |
| [`manifests/_index.md`](../manifests/_index.md) | Choosing and writing a manifest | **Canonical** |
| [`manifests/README.md`](../manifests/README.md) | Runnable preset vs. blueprint classification | **Canonical** for that classification |
| Group 1 (below) | Placeholder directory notes | **Reference** |
| Group 2 (below) | Runnable example and its sample corpus | **Reference** |
| Group 3 (below) | Module-scoped rules for Claude Code and developers | **Canonical** for their module |

Members of the grouped rows:

1. `manifests/{dev,staging,production,schema}/_index.md`
2. [`examples/simple_qa/README.md`](../examples/simple_qa/README.md),
   [`examples/hybrid_search/README.md`](../examples/hybrid_search/README.md), and their `docs/`
   corpora
3. `src/modular_rag/{contracts,orchestration,security}/CLAUDE.md`

### 3.4 Testing and validation

| Document | Purpose | Status |
|---|---|---|
| [`docs/guides/validation-protocol.md`](guides/validation-protocol.md) | Validation tiers and CI alignment | **Canonical** |
| [`docs/guides/validation.md`](guides/validation.md) | Former command inventory | **Redirect** to `validation-protocol.md` (`:3-12`), correctly self-described |
| [`.claude/rules/tests.md`](../.claude/rules/tests.md) | Test-writing rules | **Canonical** |

### 3.5 Operations

| Document | Purpose | Status |
|---|---|---|
| [`docs/guides/deployment.md`](guides/deployment.md) | Container, manifest, hardening | **Canonical** |
| [`docs/guides/backup-restore.md`](guides/backup-restore.md) | Backup, restore, rollback | **Canonical** |
| [`docs/guides/postgres-permissions.md`](guides/postgres-permissions.md) | PostgreSQL roles and permissions | **Canonical** |
| [`docs/observability/README.md`](observability/README.md) | Reference dashboard and alert material | **Canonical** index |
| [`docs/observability/runbooks.md`](observability/runbooks.md), [`slo.md`](observability/slo.md) | Runbooks and SLOs | **Canonical** |

### 3.6 Claude Code

| Document | Purpose | Status |
|---|---|---|
| [`CLAUDE.md`](../CLAUDE.md) | Non-negotiable project rules, commands, roadmap | **Canonical**; C1 resolved by Batch 6 |
| [`.claude/.instructions.md`](../.claude/.instructions.md), [`.claude/.prompt.md`](../.claude/.prompt.md), [`.claude/project-structure.md`](../.claude/project-structure.md) | Imported by `CLAUDE.md` | **Canonical** (as imports) |
| [`CLAUDE.local.example.md`](../CLAUDE.local.example.md) | Template for personal overrides | **Canonical** template |
| Group 1 (below) | Path-scoped rules | **Canonical**; all eight referenced from other docs. `adapters.md` and `agents.md` keep French headings (§5.3) |
| [`.claude/AGENTS.md`](../.claude/AGENTS.md) | Catalogue of eight specialized subagents | **Canonical** for the catalogue; the eight names match `.claude/agents/`. Filename collision with root `AGENTS.md` (§3.8 D) |
| Group 2 (below) | Subagent definitions | **Canonical**; `orchestration-specialist.md` is **Stale** — §4.1 S8 |
| Group 3 (below) | Nineteen slash-command workflows | **Canonical** per skill; `delivery-loop`'s default-path status was §4.2 C1, resolved by Batch 6 |
| [`docs/guides/claude-code.md`](guides/claude-code.md) | What is configured in this repository | **Conflicting** (§3.8 B) |
| [`docs/guides/claude-code-complete-development-guide.md`](guides/claude-code-complete-development-guide.md) | Repository workflow with worked examples | **Conflicting** (§3.8 B); declared `START HERE` by the guide below |
| [`docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md`](guides/CLAUDE-CODE-COMPLETE-GUIDE.md) | Governance-level hub | **Conflicting** (§3.8 B) and internally contradictory (§4.3 P2) |
| [`docs/guides/onboarding-claude-code.md`](guides/onboarding-claude-code.md) | First-time Claude Code setup | **Conflicting** (§3.8 B, §4.3 P1) |
| [`docs/guides/claude-code-settings-reference.md`](guides/claude-code-settings-reference.md) | Settings keys, scopes, precedence | **Reference** (general Claude Code material); silent on §5.1 |
| [`docs/guides/claude-code-advanced-config.md`](guides/claude-code-advanced-config.md) | Subagents, skills, rules, hooks | **Reference** |
| [`docs/guides/claude-code-mcp-setup.md`](guides/claude-code-mcp-setup.md) | General MCP configuration | **Reference** — self-declared generic, not project configuration |
| [`docs/guides/claude-code-plugins-marketplaces.md`](guides/claude-code-plugins-marketplaces.md) | Plugin and marketplace setup | **Reference** |
| [`docs/guides/claude-code-enterprise-deployment.md`](guides/claude-code-enterprise-deployment.md) | Organization-wide deployment | **Reference** — self-declared not configured in this project |
| [`docs/guides/subagents-parallelization.md`](guides/subagents-parallelization.md) | Using Claude Code sub-agents for parallel exploration | **Reference** (§3.8 C) |
| [`docs/guides/claude-code-parallelization-orchestration.md`](guides/claude-code-parallelization-orchestration.md) | Parallelization at tool, component, and agentic level | **Stale** — §4.1 S9; mixes tooling and framework-runtime design (§3.8 C) |
| [`docs/guides/mcp-integrations.md`](guides/mcp-integrations.md) | MCP integration governance for this repository | **Reference** |
| [`docs/guides/audit-traceability.md`](guides/audit-traceability.md) | Session and change traceability | **Reference** |
| [`docs/guides/adoption-metrics.md`](guides/adoption-metrics.md) | Claude Code adoption dashboard | **Reference** |
| [`.claude/hooks/post-edit-quality.ps1`](../.claude/hooks/post-edit-quality.ps1) | Post-edit Ruff hook (not Markdown; described by `troubleshooting.md`) | Verified present |

Members of the grouped rows:

1. `.claude/rules/{adapters,agents,contracts,health-checks,orchestration,security-layers,security,tests}.md`
2. `.claude/agents/{architecture-reviewer,generation-specialist,ingestion-specialist,observability-expert,orchestration-specialist,retrieval-specialist,security-specialist,test-specialist}.md`
3. `.claude/skills/{add-component,add-generator,add-retriever,add-security-guard,check-layering,delivery-loop,design-retriever-fusion,full-check,optimize-chunking,parallel-feature-analysis,prepare-evaluation,qa-v1,quick-check,release,run-simple-qa,test-contract,test-unit,validate-architecture,validate-security}/SKILL.md`

### 3.7 Codex, review, troubleshooting, and history

| Document | Purpose | Status |
|---|---|---|
| [`AGENTS.md`](../AGENTS.md) | Codex's reviewer role and operating rules | **Canonical** for Codex |
| [`.codex/README.md`](../.codex/README.md) | Points Codex policy to `AGENTS.md`, the workflow guide, and model routing | **Redirect** |
| [`docs/guides/ai-engineering-workflow.md`](guides/ai-engineering-workflow.md) | Five-message Claude/Codex delivery sequence | **Canonical**; C1 resolved by Batch 6 |
| [`docs/guides/model-routing.md`](guides/model-routing.md) | Provider and model-tier routing | **Canonical** |
| [`.review/handoff.example.md`](../.review/handoff.example.md), [`.review/codex-review.example.md`](../.review/codex-review.example.md) | Review templates | **Canonical**; match the structure used in practice |
| [`docs/guides/troubleshooting.md`](guides/troubleshooting.md) | Common first-week errors | **Canonical**; spot-checked references verified |
| [`docs/adr/_index.md`](adr/_index.md) | ADR index | **Canonical** index; was **Stale** — §4.1 F1, resolved by Batch 1 |
| `docs/adr/0001` … `0018` (18 files) | Architecture decisions | **Historical** records; status per file header — 17 Accepted, ADR-0004 Superseded (partial) |
| [`docs/refactoring-plan.md`](refactoring-plan.md) | Refactoring programme and dated decision log | **Canonical** for the programme; dated rows **Historical**. §1.3 heading corrected by Batch 2 (§4.1 S10) |
| Group 1 (below) | Per-lot scope and evidence | README **Canonical** index; lot files **Historical**, except `lot-22-*.md`, which is the **Canonical** scope of the in-progress lot |
| Group 2 (below) | Distilled research for design decisions | **Canonical** (required by `CLAUDE.md` rule 05.8) |
| [`docs/archive/README.md`](archive/README.md) and its five archived documents | Superseded material | **Historical** |

Members of the grouped rows:

1. [`docs/refactoring/README.md`](refactoring/README.md) and
   `docs/refactoring/lot-{0,2,3,4-public-surface-part1,4-part2-metrics-deletion-fallback,5,6-spike/README,7,8,9,10,11a,11b,11c,12a,12b,12c,13,14,15,16a,16b,16c,17,18,19,20,21,22}-*.md`,
   `technology-candidates.md`
2. [`docs/research/README.md`](research/README.md),
   `docs/research/DIGEST-{architecture,chunking,evaluation,generation,overviews,retrieval,security}.md`,
   `EVIDENCE-CATALOGUE.md`

### 3.8 Competing or colliding entry points

#### A — two framework overviews

`docs/guides/framework-overview-onboarding.md` states the same purpose as `docs/onboarding.md`
for overlapping audiences. Neither links to the other or declares precedence. `docs/_index.md`
routes to `onboarding.md`; `docs/guides/_index.md:38` routes to the other beside, not beneath,
it. **Batch 1.**

**Resolved:** Batch 1, 2026-09-20 — precedence is now declared in both directions:
`docs/onboarding.md` states it is the entry point and names the overview its companion, the
overview carries a "Where this sits" note, and `docs/guides/_index.md:38` and `docs/_index.md`
route accordingly.

#### B — four overlapping Claude Code guides with conflicting precedence

`claude-code.md` (149 lines), `claude-code-complete-development-guide.md` (173),
`CLAUDE-CODE-COMPLETE-GUIDE.md` (1,346), and `onboarding-claude-code.md` (401) all present
themselves as a starting reference.

The first draft of this audit said none of them redirects a newcomer. That was wrong (Codex pass
1, MEDIUM-001): a precedence declaration already exists, and it conflicts with another guide —
see §4.3.

**Batch 5 must reconcile the existing declarations, not add another pointer.**

**Resolved:** Batch 5, 2026-09-22 — `claude-code.md` declares the order of the four guides and
their distinct questions; the other three reference that declaration.

#### C — two parallelization guides

Resolved on a full read of both opening sections: `subagents-parallelization.md` is about Claude
Code sub-agents as a development tool, while `claude-code-parallelization-orchestration.md` mixes
tooling parallelism with framework-runtime parallelism, including a retired native multi-agent
design (§4.1 S9).

The split is genuine; the second file's scope is the problem. **Batch 5.**

**Resolved:** Batch 5, 2026-09-22 — the orchestration guide's header now separates tooling
parallelism from delegated runtime parallelism and routes readers to
`subagents-parallelization.md` for the tooling half.

#### D — identical filename, unrelated subjects

Root `AGENTS.md` holds Codex instructions; `.claude/AGENTS.md` holds the Claude Code subagent
catalogue. Their content is entirely disjoint. Anyone told to "read AGENTS.md" can open the wrong
one. **Batch 5 or 6**; no rename in scope.

**Resolved:** Batch 5, 2026-09-22 — `claude-code.md` carries a table of the two paths, their
subjects and audiences, and states why neither is renamed.

---

## 4. Verified incorrect documentation

Every row was re-verified against the cited file and line at the time of this revision. Rows marked
"pass 1" were found by Codex review pass 1; rows marked "sweep" were found by the systematic search
this revision ran in response.

**Lifecycle of a finding (amendment, 2026-09-20).** The **Claim**, **Defect** and **Verified
truth** fields keep the wording recorded at the immutable base; the defective text itself is
reproducible there (`git show 2150ce2:<file>`). **Location** is kept current, so a corrected
finding points at the text that replaced it, and a **Resolved** line names the batch that fixed
it. A finding with no **Resolved** line is still open. The plan's execution table records the
same outcome per batch.

### 4.1 Stale current-state claims

#### S1

- **Location:** `docs/guides/framework-overview-onboarding.md:93-101`, `:109`, `:136`, `:317`
- **Claim:** ADR-0015 "proposes" L0/L1/L2; cross-engine assurance "proposed, not yet implemented"
- **Verified truth:** Lot 21 is implemented: `contracts/assurance.py` exported;
  `conformance_report()` in `orchestration/native_engine.py` and
  `adapters/llms/langgraph_engine.py`. Only the Lot 22 adapter is unbuilt.
- **Found by:** pass 1 (`:94-95`, `:308`); sweep (`:103`, `:130`)
- **Resolved:** Batch 2, 2026-09-20 — the four locations now state that Lot 21 assurance levels
  are implemented on both shipped adapters and that the Lot 22 existing-application boundary is
  contract-only.
- **Batch:** 2

#### S2

- **Location:** `docs/glossary.md:278-286`
- **Claim:** "Assurance level (proposed)… These levels are not implemented today."
- **Verified truth:** Same evidence as S1.
- **Found by:** pass 1
- **Batch:** 8
- **Resolved:** Batch 8, 2026-09-23 — the entry is now "Assurance level" in the glossary's
  assurance section: the contract is implemented (`contracts/assurance.py`), both shipped engine
  adapters compute a report, and `achieved_level` is stated as computed from evidence rather than
  self-declared.

#### S3

- **Location:** `docs/glossary.md:248-258`
- **Claim:** "Lot 20 plans classification-aware, deny-by-default checks… it is not implemented
  today."
- **Verified truth:** Lot 20 is implemented: `orchestration/registry.py:42`
  `_KNOWN_REMOTE_PROVIDER_TYPES`, enforced at `:307-318`; all three runnable presets configure
  `governance.egress_policy` (`local-hybrid-rag.yaml:62`, `secure-enterprise-rag.yaml:132`,
  `langgraph-rag.yaml:95`).
- **Found by:** pass 1
- **Batch:** 8
- **Resolved:** Batch 8, 2026-09-23 — the "Provider egress" entry now states that the
  classification-aware fail-closed check is implemented, names the contract and its reference
  implementation, records that all three runnable presets configure it, and keeps the two true
  caveats: post-generation redaction does not protect this boundary, and a pipeline that
  configures no egress policy is not covered.

#### S4

- **Location:** `docs/business-case.md:131-145`
- **Claim:** Lot 20, the assurance contract, and application wrapping are "committed architecture
  direction but remain unimplemented."
- **Verified truth:** Lots 20 and 21 are implemented; only the Lot 22 adapter and pilot remain.
- **Found by:** pass 1
- **Batch:** 2
- **Resolved:** Batch 2, 2026-09-20 — the section now marks priorities 1 and 2 implemented,
  priority 3 contract-only with no way to wrap an application today, and priorities 4 and 5 open.

#### S5

- **Location:** `docs/onboarding.md:163-166`
- **Claim:** "fifteen accepted decisions… proposed assurance levels and existing-application
  support are not implementation."
- **Verified truth:** 17 of 18 ADRs are Accepted; assurance levels are implemented.
  Existing-application support is indeed not implemented.
- **Found by:** first draft (`:134`); sweep (`:135`)
- **Batch:** 1
- **Resolved:** Batch 1, 2026-09-20 — the cited lines now read "eighteen decisions, seventeen of
  them Accepted (ADR-0004 is Superseded in part)" and separate ADR status from implementation
  status.

#### S6

- **Location:** `docs/onboarding.md:232-234`, `:242-243`
- **Claim:** Security readers are pointed to "the open Lot 20 provider-egress boundary";
  "classification-aware model egress" is listed as undelivered.
- **Verified truth:** Lot 20 is implemented (S3 evidence). The same file states this correctly at
  `:388-391`, so it contradicts itself.
- **Found by:** pass 1
- **Batch:** 1
- **Resolved:** Batch 1, 2026-09-20 — both locations now state that classification-aware provider
  egress ships with Lot 20, and the second one points to section 5 instead of repeating the
  evidence.

#### S7

- **Location:** `docs/guides/framework-overview-onboarding.md:214`
- **Claim:** "live Qdrant/LLM validation remains pending"
- **Verified truth:** `CLAUDE.md` §09 V1.0 and `.github/workflows/ci.yml` (`test-integration`,
  `e2e-deterministic`) run live Qdrant/PostgreSQL; the LLM-backed scenario runs in
  `.github/workflows/nightly.yml`. The same file says "live-validated" at `:11`.
- **Found by:** pass 1 (`:207`); sweep (internal contradiction with `:11`)
- **Resolved:** Batch 2, 2026-09-20 — the "Current Status" paragraph now states that V1.0 is
  live-validated in CI, naming the integration, deterministic end-to-end and nightly LLM runs, so
  it agrees with `:11`.
- **Batch:** 2

#### S8

- **Location:** `.claude/agents/orchestration-specialist.md:42-46`
- **Claim:** "ADR-0015 assurance hooks and Lot 20 provider-egress controls remain
  proposed/planned."
- **Verified truth:** Lots 20 and 21 are implemented. This file instructs future Claude Code agent
  sessions, so the drift propagates into generated work.
- **Found by:** sweep
- **Batch:** 5
- **Resolved:** Batch 5, 2026-09-22 — the instruction now states that Lots 20 and 21 are
  implemented and must be extended rather than redesigned, and that Lot 22 is contract-only.

#### S9

- **Location:** `docs/guides/claude-code-parallelization-orchestration.md:226-253`, `:642-652`
- **Claim:** A native `agents:` manifest section (planner, retriever_agent, fact_checker) is
  "planned for V2."
- **Verified truth:** Multi-agent orchestration is delegated (ADR-0005 §5.2); the native prototype
  was removed in Lot 17; `contracts/manifests.py` has no `agents` field.
- **Found by:** sweep
- **Batch:** 5
- **Resolved:** Batch 5, 2026-09-22 — both blocks carry a dated correction stating that the
  native design was retired and that the YAML illustrates an external engine's own work, which
  this repository's schema rejects.

#### S10

- **Location:** `docs/refactoring-plan.md:217`
- **Claim:** Section heading "1.3 Proposed assurance levels"
- **Verified truth:** The levels are implemented (Lot 21). The body describes them accurately;
  only the heading is stale.
- **Found by:** sweep
- **Batch:** 2
- **Resolved:** Batch 2, 2026-09-20 — the heading now reads "1.3 Assurance levels (implemented in
  Lot 21)".

### 4.2 Contradictions between canonical sources

#### C1

- **Location:** `CLAUDE.md:170-178` vs. `docs/guides/ai-engineering-workflow.md:394-402`
- **Contradiction:** `CLAUDE.md` says "For normal delivery, prefer the single `/delivery-loop`
  skill." The canonical workflow guide says `/delivery-loop`, `prepare_review.ps1`, and
  `run_codex_review.ps1` are retained "for optional future automation. They are not part of the
  current default workflow," and that the five-message chat workflow is the supported path. A
  newcomer following `CLAUDE.md` reaches the non-default automation first.
- **Batch:** 6
- **Resolved:** Batch 6, 2026-09-22 — both documents now state that the five-message chat
  workflow is the default and that `/delivery-loop` and the two scripts are optional automation
  of the same sequence. `claude-code.md`, which also called the skill the preferred entry point,
  was aligned.

### 4.3 Conflicting precedence declarations

#### P1

- **Location:** `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md:513` vs.
  `docs/guides/onboarding-claude-code.md:10`
- **Problem:** The largest guide labels `claude-code-complete-development-guide.md` the
  **CURRENT WORKFLOW** and says "START HERE if you're building a feature or joining the team."
  `onboarding-claude-code.md` presents itself as the guide for using Claude Code "for the first
  time" with its own "Files to read first." A new team member receives two different starting
  points. (Codex pass 1, MEDIUM-001.)
- **Batch:** 5
- **Resolved:** Batch 5, 2026-09-22 — one declared order now lives in `claude-code.md`, "Which
  Claude Code guide to read", and the four guides point to it instead of each claiming the
  start.

#### P2

- **Location:** `docs/guides/CLAUDE-CODE-COMPLETE-GUIDE.md:543-548`
- **Problem:** Line 541 calls its 5-step workflow "the canonical scheme — the single source of
  truth for step names and ordering." Lines 543-547 then say those steps are "a general
  task-planning aid" and that the authoritative workflow lives in
  `claude-code-complete-development-guide.md`, `ai-engineering-workflow.md`, and `CLAUDE.md`. The
  paragraph contradicts itself.
- **Batch:** 5
- **Resolved:** Batch 5, 2026-09-22 — the paragraph no longer calls itself the single source of
  truth; it is a general task-planning aid and names the two authoritative workflows.

### 4.4 Other factual and formatting defects

#### F1

- **Location:** `docs/adr/_index.md:334`
- **Defect:** "Eighteen ADRs are Accepted."
- **Evidence:** Status headers: 17 Accepted, ADR-0004 Superseded (partial). Contradicts
  `onboarding.md:134` (S5) as well as the files themselves.
- **Batch:** 1
- **Resolved:** Batch 1, 2026-09-20 — the cited line now reads "Eighteen ADRs exist; seventeen are
  Accepted, and ADR-0004 is Superseded (partial) by ADR-0005."


#### F2

- **Location:** `docs/guides/getting-started.md:125`
- **Defect:** `secure-enterprise-rag.yaml` "does not yet enforce Lot 20 provider-egress policy."
- **Evidence:** The manifest declares `governance.egress_policy` at `:132` (S3 evidence).
- **Batch:** 2
- **Resolved:** Batch 2, 2026-09-20 — the preset row now states that the manifest declares a
  `governance.egress_policy`, so Lot 20 control applies.

#### F3

- **Location:** `docs/guides/getting-started.md:122-128`
- **Defect:** Two prose lines sit between rows of the preset table, splitting it; the two
  blueprint rows lose their header.
- **Evidence:** Direct read. The prose itself is accurate.
- **Batch:** 4
- **Resolved:** Batch 4, 2026-09-21 — the two prose lines moved below the table, which now runs
  from `:122` to `:128` with its blueprint rows under the same header.

### 4.5 Claims verified accurate (no correction needed)

- `docs/guides/installation.md` — all nine extras groups match `pyproject.toml`.
- `docs/guides/troubleshooting.md` — hook path, `core.protectNTFS` procedure, layering-audit
  behaviour.
- `CONTRIBUTING.md` — `scripts/check.sh`, `check.ps1`, `install_git_hooks.{ps1,sh}`,
  `check_docs.py`, `check_layering.py`, and `.githooks/pre-push` all exist and behave as described.
- `docs/architecture/_index.md:44-48`, `security.md:25`/`:84`/`:255-263`,
  `document-engine-contract.md:9-14`/`:113`, and `data-classification-policy.md:74` — Lot 20–22
  statements accurate.
- `docs/onboarding.md:433-436` — Lot 20–22 statement accurate (but see S6).
- `.claude/AGENTS.md` — eight subagent names match `.claude/agents/`.
- `.review/*.example.md` — match the structure used in practice.
- `ROADMAP.md`, `README.md`, `CLAUDE.md` §01/§09, `capability-matrix.md`, and `overview.md` —
  Lot 20–22 status consistent with the code as of the base commit.

---

## 5. Missing operational knowledge

These are gaps: nothing written is wrong, but something a newcomer needs is not written down.

### 5.1 The shared-settings rewrite hazard

Approving a Claude Code command at **project scope** makes the permission mechanism rewrite the
shared `.claude/settings.json`: it adds the command to `permissions.allow`, auto-approving it for
every contributor who pulls the change, and silently drops `hooks.PostToolUse[0].description`.

This recurred at least three times in the sessions immediately preceding this audit, and each
time the grants had to be moved to the gitignored `.claude/settings.local.json` and the
description restored before a commit was safe.

None of `docs/guides/claude-code-settings-reference.md`, `claude-code.md`,
`claude-code-advanced-config.md`, or `CLAUDE.md` documents the mechanism or the mitigation
(approve at local scope). The absence is checkable in the repository; the recurrence is session
observation. **Batch 5.**

**Resolved:** Batch 5, 2026-09-22 — `claude-code.md` documents the mechanism, the local-scope
mitigation, the `git diff` check before committing, and the hook-description restoration.

### 5.2 Branch-naming table omits an in-use prefix

`CONTRIBUTING.md:30-38` lists `feature/`, `fix/`, `docs/`, `refactor/`, `test/`. Recently merged
configuration changes used `chore/`, which `CONTRIBUTING.md:82` already allows as a commit type
but not as a branch prefix. **Batch 7.**

**Resolved:** Batch 7, 2026-09-23 — the branch table gains `chore/` and `ci/`, and the commit-type
list gains `ci`, which merged history used five times without documenting it. Both lists now say
they describe what the repository actually uses.

### 5.3 Untranslated rule files

`.claude/rules/contracts.md`, `security.md`, and `tests.md` carry a note that the rules were
translated to English on 2026-08-06. `.claude/rules/adapters.md:9` ("Règles — édition des
adaptateurs") and `.claude/rules/agents.md:9` ("Règles — édition du module agents") still have
French headings. Whether the bodies are also untranslated was not verified. **Batch 5.**

**Resolved:** Batch 5, 2026-09-22 — both headings are translated, each with a dated note; a
repository-wide search found no other French heading under `.claude/rules/`, and both bodies
were already English.

---

## 6. Capability status verified against code

Recorded so later batches need not re-derive the evidence. Written with the §2 vocabulary.

| Capability | Status |
|---|---|
| Lot 20 — classification-aware provider egress | `implemented` |
| Lot 21 — L0/L1/L2 assurance contract and conformance report | `implemented` |
| Lot 22 — existing-application adapter boundary | `contract-only` |
| Lot 22 — behavioural fixture, pilot adapter, comparative pilot | `planned` |
| Engine selection behind `DocumentEngine` (native or LangGraph) | `implemented` |
| V2.1 — multi-agent orchestration | `planned (delegated)` |
| V3.0 — GraphRAG traversal | `planned (delegated)` |
| V5.0 — multimodal execution | `planned (delegated)` |
| Codex two-pass review workflow | `implemented` |
| Claude Code subagent catalogue | `implemented` |

**Evidence**

- **Lot 20 — classification-aware provider egress:** `contracts/egress.py` exported;
  `orchestration/registry.py:42`, `:307-318`; all three runnable presets configure
  `governance.egress_policy`.
- **Lot 21 — L0/L1/L2 assurance contract and conformance report:** `contracts/assurance.py`
  exported; `conformance_report()` on both shipped adapters.
- **Lot 22 — existing-application adapter boundary:** `contracts/application.py` exported with 43
  passing tests; no `adapters/applications/`; `app/bootstrap.py` constructs only `native` and
  `langgraph`; no manifest can select an application adapter.
- **Lot 22 — behavioural fixture, pilot adapter, comparative pilot:** No corresponding code;
  `docs/refactoring/lot-22-*.md` scope only.
- **Engine selection behind `DocumentEngine` (native or LangGraph):** `app/bootstrap.py`
  `load_engine()`; `manifests/presets/langgraph-rag.yaml`.
- **V2.1 — multi-agent orchestration:** Delegated by ADR-0005 §5.2. The shipped LangGraph adapter
  is a fixed route → retrieve → guard → generate graph without planning, tools, decomposition, or
  collaborating agents (`getting-started.md:126`, `CLAUDE.md` §09). Native prototype removed in
  Lot 17.
- **V3.0 — GraphRAG traversal:** Delegated by ADR-0005 §5.2. No native graph capability (ADR-0007
  Étape 8); `manifests/blueprints/graph-memory-rag.yaml` is a blueprint, and the selected engine
  does not provide it (`getting-started.md:127`).
- **V5.0 — multimodal execution:** Delegated by ADR-0005 §5.2;
  `manifests/blueprints/multimodal-rag.yaml` is a blueprint; `embedder.type: multimodal` is not a
  registered factory.
- **Codex two-pass review workflow:** `.review/*.example.md` and `ai-engineering-workflow.md`
  match practice (subject to §4.2 C1).
- **Claude Code subagent catalogue:** Eight files in `.claude/agents/`, all named in
  `.claude/AGENTS.md`.

---

## 7. Acceptance criteria for this batch

- [x] Every onboarding-related document has a declared purpose and canonical/non-canonical status
      — §3.1–3.7, member by member; grouped rows name every member.
- [x] Every subject has an identified canonical source or a recorded source-of-truth gap — §3
      status column; gaps in §3.8, §4.2, and §4.3.
- [x] Every material capability claim is backed by a repository reference — §4 and §6.
- [x] Contradictions and stale claims identify their exact file and evidence — §4.1–4.4.
- [x] Missing knowledge is separated from incorrect documentation — §5 versus §4.
- [x] Recommendations are assigned to future batches — §4 "Batch" columns and §8.
- [x] No implementation or existing guide was modified — only this audit and the Batch 0 fields of
      `docs/onboarding-overhaul-plan.md` changed.

**Limit stated rather than hidden.** Status drift was located by repository-wide searches for
current-state wording (Lot 20/21/22, egress, assurance, conformance, live validation, ADR counts,
native agent designs), followed by a read of every hit in context.

Documents were not all read end to end; a stale claim phrased without any of those terms could
still exist. Later batches that rewrite a document must read it in full regardless.

---

## 8. Recommendations by batch

| Batch | Findings |
|---|---|
| 1 — Canonical navigation | §3.8 A; S5; S6; F1 — all resolved by Batch 1, 2026-09-20 |
| 2 — Vision and status | S1; S4; S7; S10; F2 — all resolved by Batch 2, 2026-09-20 |
| 4 — Local environment | F3 — resolved by Batch 4, 2026-09-21 |
| 5 — Claude Code | §3.8 B, C, D; S8; S9; P1; P2; §5.1; §5.3 — all resolved by Batch 5, 2026-09-22 |
| 6 — Codex and AI delivery | §3.8 D (resolved by Batch 5); C1 — resolved by Batch 6, 2026-09-22 |
| 7 — Recipes and validation | §5.2 — resolved by Batch 7, 2026-09-23 |
| 8 — Concepts | S2; S3 |

---

## 9. This batch's own status

Mirrored in `docs/onboarding-overhaul-plan.md`:

- **Status:** `COMPLETE` — pass 1 returned `CHANGES_REQUIRED` (two HIGH, one MEDIUM); the
  corrections in this revision were closed by pass 2, which returned
  `READY_FOR_FINAL_VALIDATION`. Delivery approved by the maintainer on 2026-09-17.
- **Owner:** Claude Code
- **Reviewer:** Codex
- **Evidence:** this document; the pass-1 and pass-2 Codex reports and the review handoff (local,
  gitignored review artifacts)
