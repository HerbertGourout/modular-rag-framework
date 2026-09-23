# Developer Onboarding Overhaul Plan

**Status:** Proposed  
**Scope:** Documentation and onboarding only  
**Execution model:** Sequential batches, one writer and one reviewer  
**Primary audience:** Developers joining the project without prior context

## 1. Objective

Create a complete, self-guided developer onboarding path that allows a new contributor to become
operational without relying on undocumented knowledge from the project lead.

The onboarding must cover the current product vision, the implemented system, the development
environment, repository conventions, Claude Code and Codex configuration, the delivery workflow,
validation, troubleshooting, and the first contribution. It must be ordered as a learning journey:

```text
Understand
  -> prepare access and tools
  -> install
  -> run
  -> inspect the architecture and code
  -> understand governance and assurance
  -> use Claude Code and Codex safely
  -> modify
  -> validate
  -> review
  -> deliver
  -> troubleshoot independently
```

This is not a request to reproduce the full history of every commit, pull request, or refactoring.
Historical information is included only when it explains a structural decision that still shapes
the current system.

## 2. Success Criteria

The overhaul is complete only when a developer unfamiliar with the repository can, using the
repository alone:

1. explain the framework's current purpose, positioning, non-goals, and maturity;
2. distinguish implemented, partial, contract-only, delegated, and planned capabilities;
3. install the supported local environment and verify it with documented expected results;
4. run the native reference path and identify when external services or paid credentials are
   required;
5. trace ingestion and query execution through the codebase;
6. explain the hexagonal boundaries and place a change in the correct module;
7. understand identity, tenant isolation, PII, classification, provider egress, audit, evidence,
   assurance, and conformance;
8. configure and use Claude Code and Codex according to repository policy;
9. execute the bounded Claude/Codex implementation and two-pass review workflow;
10. select and run the appropriate local and CI validation tier;
11. prepare a compliant pull request without undocumented intervention;
12. diagnose the common failures covered by the repository;
13. know when a human decision is mandatory.

## 3. Non-Goals

- Recount every project change chronologically.
- Turn `README.md` into a complete manual.
- Duplicate detailed architecture, API, operations, or ADR content in the onboarding hub.
- Present planned capabilities as implemented.
- Invent business concepts that are not represented in the current contracts or code.
- Document personal credentials, local secrets, or machine-specific configuration.
- Change implementation behavior as part of this documentation programme.

## 4. Sources of Truth

Every onboarding claim must be verified against the highest applicable source below:

1. executable code, manifests, tests, and CI workflows;
2. accepted ADRs and public contracts;
3. `CLAUDE.md`, `AGENTS.md`, path-specific rules, and checked-in tool configuration;
4. `ROADMAP.md` and the current refactoring plan;
5. guides and indexes;
6. Git history, only when current sources do not explain a still-relevant decision.

When sources disagree, the implementation and accepted decisions take precedence. The conflict
must be corrected or explicitly recorded; it must not be silently reconciled by assumption.

## 5. Roles and Change Protocol

The repository's normal one-writer/one-reviewer model applies to every batch.

| Responsibility | Claude Code | Codex | Human |
|---|---|---|---|
| Implement one documentation batch | Sole writer | No implementation edits during review | Authorizes scope |
| Verify claims against code and configuration | Required | Challenges evidence | Resolves ambiguity |
| Prepare `.review/handoff.md` | Owns | Reads | Checks readiness |
| Review the complete batch diff | Self-review | Independent reviewer | Arbitrates findings |
| Apply accepted corrections | Owns | Verifies in closure pass | Approves decisions |
| Commit, push, merge, or release | Only when explicitly asked | Never during review | Owns |

Each batch must follow `docs/guides/ai-engineering-workflow.md`. Codex review is bounded to one
discovery pass and, when corrections are required, one closure-only pass. Documentation changes
must not be mixed with unrelated implementation changes.

## 6. Progress States

Use only these values in the execution table:

- `NOT_STARTED`
- `IN_PROGRESS`
- `READY_FOR_REVIEW`
- `CHANGES_REQUIRED`
- `COMPLETE`
- `BLOCKED`

A batch becomes `COMPLETE` only after its acceptance criteria and applicable validations pass.

## 7. Sequential Execution Plan

The batches below are dependency ordered. Do not begin a later batch while an earlier batch has
unresolved blocking findings, because later documents depend on the vocabulary and navigation
established earlier.

### Batch 0 — Baseline and documentation truth map

**Status:** `COMPLETE` — see
[`docs/onboarding-baseline-audit-2026-09-17.md`](onboarding-baseline-audit-2026-09-17.md)

**Purpose:** Establish a verified baseline before rewriting navigation or onboarding prose.

**Work:**

- Inventory onboarding, architecture, development, testing, operations, Claude Code, Codex, and
  contribution documentation.
- Map duplicated subjects and identify the canonical source for each subject.
- Verify capability status against code, manifests, tests, ADRs, and CI.
- Record contradictions, stale statements, broken links, and missing operational knowledge.
- Identify repository knowledge that still exists only in the project lead's memory.
- Define the controlled vocabulary for capability states: `implemented`, `partial`,
  `contract-only`, `delegated`, and `planned`.

**Expected files:**

- `docs/documentation-alignment-audit-*.md` or a successor audit artifact
- this plan's execution table

**Acceptance criteria:**

- Every onboarding-related document has a declared purpose and canonical/non-canonical status.
- Every material capability claim is backed by a repository reference.
- No implementation file is modified.

### Batch 0.5 — Documentation foundation

**Status:** `COMPLETE` — see
[`docs/guides/documentation-style-guide.md`](guides/documentation-style-guide.md)

**Purpose:** Establish one shared documentation standard, and the project skills that apply it,
before any onboarding document is rewritten, so later batches do not reproduce the current
dense layout.

**Work:**

- Write a style guide covering readability, fidelity, the capability status vocabulary, and
  references to other files.
- Add three project skills that execute the guide: writing, editorial form review, and
  pre-handoff truth verification.
- Keep form review and truth verification as separate responsibilities; truth verification is
  the writer's self-check and never replaces Codex review.
- Reference the guide from this plan's per-batch handoff template.

**Expected files:**

- `docs/guides/documentation-style-guide.md`
- `.claude/skills/write-documentation/SKILL.md`
- `.claude/skills/review-documentation-quality/SKILL.md`
- `.claude/skills/verify-documentation-truth/SKILL.md`
- `docs/guides/_index.md` and `docs/guides/claude-code.md`, for navigation and the skill list
- this plan

**Acceptance criteria:**

- The style guide exists and itself complies with its rules.
- The three skills reference the guide instead of copying its rules.
- Every later batch's handoff applies the guide.

Editorial warnings in `scripts/check_docs.py` are a separately authorized follow-up; they are not
part of this batch.

### Batch 1 — Canonical onboarding navigation

**Status:** `COMPLETE` — see [`docs/onboarding.md`](onboarding.md)

**Purpose:** Make one document the unambiguous entry point for a new developer.

**Work:**

- Recast `docs/onboarding.md` as the canonical learning path.
- Define required, role-specific, and reference-only reading.
- Add an explicit sequence from vision to first contribution.
- Explain which documents are sources of truth and which are summaries.
- Align `README.md`, `docs/_index.md`, and `docs/guides/_index.md` with that path.
- Remove competing entry-point language without deleting useful specialist content.

**Expected files:**

- `docs/onboarding.md`
- `README.md`
- `docs/_index.md`
- `docs/guides/_index.md`

**Acceptance criteria:**

- All primary entry points direct a newcomer to the same onboarding path.
- A newcomer can determine the next document without choosing between overlapping guides.
- Detailed references remain linked rather than copied into the hub.

### Batch 2 — Current vision, capability status, and limits

**Status:** `COMPLETE` — see
[`docs/architecture/capability-matrix.md`](architecture/capability-matrix.md)

**Purpose:** Explain the project as it exists now, without requiring knowledge of its refactoring
history.

**Work:**

- State the portable assurance and delivery positioning.
- Explain the bounded native reference engine, owned control plane, delegated engines, and
  external-application direction.
- State the product hypothesis and what still requires comparative evidence.
- Add a capability matrix using the controlled status vocabulary.
- Separate current capabilities from roadmap targets and contract-only boundaries.
- Explain explicit non-goals and avoid competitive claims unsupported by measured evidence.
- Include only the small amount of history needed to explain the current boundary.

**Expected files:**

- `docs/onboarding.md`
- `README.md`
- `docs/business-case.md`
- `docs/architecture/capability-matrix.md`
- `ROADMAP.md`, only where status reconciliation is required

**Acceptance criteria:**

- Lot 20, Lot 21, and Lot 22 status is consistent everywhere in scope.
- No text implies that an existing external application can already be wrapped when only the
  contract exists.
- Delegated capabilities are not described as native implementations.

### Batch 3 — Architecture and code learning path

**Status:** `COMPLETE` — see [`docs/guides/code-walkthrough.md`](guides/code-walkthrough.md)

**Purpose:** Let a developer move from the system view to the relevant source files safely.

**Work:**

- Present the current architecture in execution order.
- Document the ingestion and query flows from entry point to evidence and audit.
- Explain package responsibilities and allowed dependency directions.
- Identify the extension path for contracts, domain components, adapters, factories, manifests,
  CLI commands, API routes, and conformance tests.
- Link structural decisions to the relevant ADRs without requiring all ADRs as prerequisite
  reading.
- Verify every named type, function, module, and manifest against the current tree.

**Expected files:**

- `docs/guides/code-walkthrough.md`
- `docs/architecture/overview.md`
- `docs/architecture/module-model.md`
- `docs/architecture/structure.md`
- `docs/architecture/runtime-flow.md`
- `.claude/project-structure.md`

**Acceptance criteria:**

- A developer can trace one ingestion and one query path to actual source files.
- Layer rules in the guides match `scripts/check_layering.py` and `CLAUDE.md`.
- Each common extension type identifies its implementation, wiring, and test locations.

### Batch 4 — Local environment and first execution

**Status:** `COMPLETE` — see [`docs/guides/installation.md`](guides/installation.md)

**Purpose:** Provide reproducible setup from a clean supported workstation.

**Work:**

- Consolidate prerequisites, Python environment creation, extras, Docker services, environment
  variables, and verification commands.
- Distinguish deterministic local execution from tests requiring Qdrant, PostgreSQL, network
  access, or paid model credentials.
- Cover Windows first where repository tooling is Windows-specific, while retaining supported
  Linux and macOS instructions.
- Add expected results and recovery steps for each setup checkpoint.
- Explain local-only configuration, secret handling, and ignored files.
- Verify CLI, API, and `examples/simple_qa` startup instructions.

**Expected files:**

- `docs/guides/installation.md`
- `docs/guides/getting-started.md`
- `docs/guides/troubleshooting.md`
- `.env.example`
- `CONTRIBUTING.md`

**Acceptance criteria:**

- A clean-room setup checklist exists with observable success conditions.
- Commands identify their working directory, prerequisites, and external-service requirements.
- No real key, personal path, or secret appears in tracked documentation.

### Batch 5 — Claude Code configuration and operating model

**Status:** `COMPLETE` — see [`docs/guides/claude-code.md`](guides/claude-code.md)

**Purpose:** Make the checked-in Claude Code development environment understandable and safe to
use without oral guidance.

**Work:**

- Explain instruction precedence and the roles of `CLAUDE.md`, imported instructions,
  path-specific `CLAUDE.md` files, and `.claude/rules/`.
- Document `.claude/settings.json`, hooks, permissions, ask/allow/deny boundaries, and local
  overrides without copying unstable configuration values into multiple guides.
- Inventory project skills and state when each one should be used.
- Explain subagent constraints, single-writer ownership, and safe parallel analysis.
- Document prompt preparation, task scoping, acceptance criteria, stopping conditions, and human
  approval boundaries.
- Distinguish project configuration from personal configuration and enterprise policy.

**Expected files:**

- `docs/guides/onboarding-claude-code.md`
- `docs/guides/claude-code.md`
- `docs/guides/claude-code-complete-development-guide.md`
- `docs/guides/claude-code-advanced-config.md`
- `docs/guides/claude-code-settings-reference.md`
- `CLAUDE.md` and `.claude/**`, only when a verified documentation/configuration mismatch requires
  correction

**Acceptance criteria:**

- Every checked-in Claude workflow relevant to normal development is discoverable.
- Permission and human-decision boundaries are explained accurately.
- Personal or enterprise-only options are not presented as repository defaults.
- A developer can prepare a bounded implementation request without help.

### Batch 6 — Codex configuration and the complete AI delivery loop

**Status:** `COMPLETE` — see
[`docs/guides/ai-engineering-workflow.md`](guides/ai-engineering-workflow.md)

**Purpose:** Teach developers how implementation, independent review, remediation, validation,
and human delivery decisions fit together.

**Work:**

- Explain `AGENTS.md`, the Codex reviewer role, and any checked-in Codex-specific configuration.
- Explain `.review/handoff.md`, `.review/codex-review.md`, and their templates.
- Document discovery pass, correction batch, closure-only pass, final bounded Claude remediation,
  and the two-pass stop condition.
- Explain severity, finding disposition, immutable base, corrective base, and causal evidence.
- Cover both the supported chat workflow and optional repository automation.
- State clearly that deterministic validation and human authorization remain final authorities.
- Provide copy-ready prompts only in the canonical AI workflow guide.

**Expected files:**

- `AGENTS.md`
- `docs/guides/ai-engineering-workflow.md`
- `docs/guides/model-routing.md`
- `.review/handoff.example.md`
- `.review/codex-review.example.md`
- Codex configuration documentation, if checked-in configuration exists

**Acceptance criteria:**

- A developer can execute the complete normal path and correction path without oral guidance.
- Writer, reviewer, and human responsibilities are unambiguous.
- No guide recommends a third general Codex review.
- Commit, push, merge, paid calls, destructive actions, and risk acceptance remain human-controlled.

### Batch 7 — Daily development recipes and validation matrix

**Status:** `NOT_STARTED`

**Purpose:** Convert repository conventions into executable task recipes.

**Work:**

- Document bounded recipes for a bug fix, component, adapter, contract change, manifest change,
  ADR, documentation-only change, and hotfix.
- For each recipe, list preconditions, expected files, mandatory tests, documentation impact,
  review requirements, and completion criteria.
- Consolidate quick, targeted, full, integration, e2e, benchmark, layering, security, and release
  validation tiers.
- Explain CI jobs and the local equivalent where one exists.
- Identify checks that require services, credentials, network access, or explicit authorization.
- Align Git branch, commit, pull request, and review conventions.

**Expected files:**

- `CONTRIBUTING.md`
- `docs/guides/validation.md`
- `docs/guides/validation-protocol.md`
- `docs/guides/ai-engineering-workflow.md`
- relevant testing rules under `.claude/rules/`

**Acceptance criteria:**

- Every common change type has one documented route from task definition to delivery decision.
- Validation commands match scripts and CI rather than remembered conventions.
- The distinction between unavailable, skipped, and failed validation is explicit.

### Batch 8 — Concepts and terminology

**Status:** `NOT_STARTED`

**Purpose:** Give all contributors one vocabulary grounded in current contracts and behavior.

**Work:**

- Group concepts by data, execution, security, governance, assurance, integration, and quality.
- Define each term, point to its authoritative contract or implementation, and record common
  confusions.
- Cover at least Document, Chunk, Query, Answer, Citation, identity, tenant, roles, PII,
  classification, policy, egress, audit, trace, evidence, conformance, assurance level, engine,
  capability, adapter, control point, benchmark, golden set, quality gate, and regression.
- Do not introduce concepts such as conversation, session, or benefits mode unless current code or
  an accepted decision makes them part of this project.

**Expected files:**

- `docs/glossary.md`
- `docs/onboarding.md`, for a minimal prerequisite concept map

**Acceptance criteria:**

- Every mandatory onboarding concept has exactly one canonical definition.
- Definitions do not overstate security, privacy, or compliance guarantees.
- Terms absent from the product are explicitly excluded rather than invented.

### Batch 9 — Five-day autonomous learning path

**Status:** `NOT_STARTED`

**Purpose:** Turn the preceding references into a practical first-week programme.

**Work:**

- Day 1: vision, access, setup, and first deterministic execution.
- Day 2: ingestion, query flow, architecture, and repository navigation.
- Day 3: governance, security, egress, audit, assurance, and current limitations.
- Day 4: Claude Code, Codex, handoff, review, remediation, and validation.
- Day 5: a bounded first contribution from branch creation to pull-request readiness.
- Give each day required reading, commands, exercises, expected evidence, and completion checks.
- Provide optional deeper tracks for architecture, security, evaluation, and operations.

**Expected files:**

- `docs/onboarding.md`
- specialist guides linked by the daily exercises

**Acceptance criteria:**

- Each exercise can be completed without unpublished data or paid credentials unless clearly
  marked optional.
- Each day ends with observable evidence, not only reading.
- The final exercise uses the real contribution and review rules.

### Batch 10 — Deduplication, clean-room validation, and maintenance gate

**Status:** `NOT_STARTED`

**Purpose:** Remove contradictory routes, prove autonomy, and prevent documentation drift.

**Work:**

- Replace duplicated normative instructions with links to the canonical source.
- Archive or label superseded onboarding material without erasing useful history.
- Run link, formatting, terminology, status, and command checks available in the repository.
- Have a developer unfamiliar with the project execute the onboarding from a clean environment.
- Record every question that required project-lead intervention and close the corresponding gap.
- Add documentation-impact checks to pull-request and delivery guidance.
- Define who updates capability status, tool configuration, validation commands, and onboarding
  exercises after future changes.

**Expected files:**

- all onboarding entry points and affected specialist guides
- contribution and pull-request checklists
- documentation validation scripts or CI only if separately scoped and approved

**Acceptance criteria:**

- A clean-room user completes the success criteria in section 2.
- Primary documentation contains no known contradictory capability status.
- All referenced commands and paths exist.
- Future feature completion requires updating capability status and affected onboarding steps.

## 8. Execution Table

Update this table at the end of each approved batch. Evidence should link to the handoff, review,
validation output, or merged pull request rather than relying on a narrative claim.

| Batch | Status | Owner | Reviewer | Evidence | Notes / blockers |
|---|---|---|---|---|---|
| 0 — Baseline and truth map | `COMPLETE` | Claude Code | Codex (pass 1: `CHANGES_REQUIRED`; pass 2: `READY_FOR_FINAL_VALIDATION`, all findings closed) | [`docs/onboarding-baseline-audit-2026-09-17.md`](onboarding-baseline-audit-2026-09-17.md), `.review/handoff.md` | Inventory covers every in-scope cluster; 10 stale status claims, 1 canonical-source contradiction, 2 conflicting precedence declarations, 3 factual/formatting defects, 3 knowledge gaps. None corrected here — assigned to Batches 1, 2, 4, 5, 6, 7, 8 (audit §8) |
| 0.5 — Documentation foundation | `COMPLETE` | Claude Code | Codex (pass 1: `CHANGES_REQUIRED`, two HIGH; pass 2: `READY_FOR_FINAL_VALIDATION`, all findings closed) | [`docs/guides/documentation-style-guide.md`](guides/documentation-style-guide.md), `.review/handoff.md` | Style guide and three documentation skills; editorial warnings in `scripts/check_docs.py` follow as a separate change |
| 1 — Canonical navigation | `COMPLETE` | Claude Code | Codex (pass 1: `CHANGES_REQUIRED`, two HIGH and one MEDIUM; pass 2: `READY_FOR_FINAL_VALIDATION`, all closed) | [`docs/onboarding.md`](onboarding.md), `.review/handoff.md` | Entry point declared in five phases with per-profile depth; authority order aligned with §4; audit findings §3.8 A, S5, S6 and F1 resolved and recorded in the audit's lifecycle notes |
| 2 — Vision and status | `COMPLETE` | Claude Code | Codex (pass 1: `CHANGES_REQUIRED`, two HIGH; pass 2: `READY_FOR_FINAL_VALIDATION`, all closed) | [`docs/architecture/capability-matrix.md`](architecture/capability-matrix.md), `.review/handoff.md` | Audit findings S1, S4, S7, S10 and F2 resolved; four-state vocabulary in the onboarding hub and a bridge to it in the capability matrix |
| 3 — Architecture and code | `COMPLETE` | Claude Code | Codex (pass 1 and pass 2: `CHANGES_REQUIRED`, two HIGH each; closed by the bounded final remediation, not re-reviewed) | [`docs/guides/code-walkthrough.md`](guides/code-walkthrough.md), `.review/handoff.md` | Egress checkpoints added to both runtime diagrams; extension table per change type; `observability/` layering case documented |
| 4 — Local environment | `COMPLETE` | Claude Code | Codex (pass 1: `CHANGES_REQUIRED`, three HIGH and one MEDIUM; pass 2: `CHANGES_REQUIRED`, one HIGH open plus one MEDIUM regression, both closed by the bounded final remediation, not re-reviewed) | [`docs/guides/installation.md`](guides/installation.md), `.review/handoff.md` | Clean-room checklist, per-run service/credential table, secrets handling, audit finding F3. `.env.example` is listed in the batch but is unreadable under the repository's own `deny(**/.env*)` rule; the human kept it out of scope |
| 5 — Claude Code | `COMPLETE` | Claude Code | Codex (pass 1 and pass 2: `CHANGES_REQUIRED`; closed by the bounded final remediation, not re-reviewed) | [`docs/guides/claude-code.md`](guides/claude-code.md), `.review/handoff.md` | Nine audit findings: §3.8 B, C, D, S8, S9, P1, P2, §5.1, §5.3. Also corrected `.claude/.instructions.md`, which every session imports |
| 6 — Codex and AI delivery | `COMPLETE` | Claude Code | Codex (pass 1 and pass 2: `CHANGES_REQUIRED`; closed by the bounded final remediation, not re-reviewed) | [`docs/guides/ai-engineering-workflow.md`](guides/ai-engineering-workflow.md), `.review/handoff.md` | Audit finding C1 resolved across three documents; review vocabulary and a working no-checkpoint corrective-base procedure documented |
| 7 — Recipes and validation | `NOT_STARTED` | — | — | — | Depends on Batches 3–6 |
| 8 — Concepts | `NOT_STARTED` | — | — | — | Depends on Batches 2–3 |
| 9 — Five-day path | `NOT_STARTED` | — | — | — | Depends on Batches 2–8 |
| 10 — Final validation | `NOT_STARTED` | — | — | — | Depends on all prior batches |

## 9. Per-Batch Handoff Template

Each batch request sent to Claude should provide:

```text
Onboarding overhaul — Batch <number>: <title>

Objective:
<one observable outcome from this plan>

Exact scope:
<files and sections authorized for this batch>

Out of scope:
- implementation behavior changes
- unrelated documentation modernization
- capability claims not proven by the repository

Acceptance criteria:
<copy the batch criteria and add task-specific checks>

Required validation:
- verify every path, command, type, and capability claim against the repository
- run the repository's documentation checks
- run targeted tests only when examples or executable commands require them
- prepare `.review/handoff.md` for Codex pass 1

Constraints:
- apply docs/guides/documentation-style-guide.md
- preserve unrelated working-tree changes
- use one writer
- do not commit or push without explicit authorization
```

The standard prompts and review limits remain defined in
`docs/guides/ai-engineering-workflow.md`; this plan does not duplicate or supersede them.

## 10. Change Control

- The human owner may split a batch when its diff becomes too broad, but must preserve dependency
  order and acceptance criteria.
- A batch may be combined with the immediately following batch only when both affect the same
  documents and the resulting review remains bounded.
- Any discovered implementation defect must be recorded separately. It must not be silently fixed
  inside this documentation programme.
- Any change to a public contract, security policy, dependency, production manifest, or CI
  behavior requires a separately authorized task.
- This plan is complete when Batch 10 is complete; it is not an evergreen substitute for the
  onboarding documents it creates.
