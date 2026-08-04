# Lot 2 — Interim Claude Configuration Realignment

**Status:** COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 1 (ADR-0005, accepted 2026-08-04)
**Gates:** none further — Lot 3 was already in progress in parallel

This is the Lot 2 deliverable: a narrow realignment of `CLAUDE.md` and `.claude/` so they stop
steering implementation toward capabilities [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)
delegates to a selected external engine, without doing the full rewrite reserved for Lot 17. Two
Explore agents inventoried the repo first (2026-08-03/04); this table records what happened to
each file they flagged.

## Decision record

| File | Disposition | What changed / why |
|---|---|---|
| `CLAUDE.md` (root) | **Modified** | §01 note pointing to ADR-0005; §09 superseding note above the roadmap table; Adapter Stubs table reworked (llms/graphstores/search now "reachable" not "reserved"; auth flagged "not yet assigned"); Implementation Order note distinguishing native-sequence gating from delegation lots; Key Differentiators table marked delegated rows with ⚙️ |
| `.claude/.instructions.md` | **Modified** | §5 `agents/` row reframed as adapter-integration, not native coordinator; §7 "V2+ (Future)" reframed as "delegated, not deferred," with Policy Engine called out as *not* delegated; §8 ADR list gained ADR-0005 |
| `.claude/settings.json` | **Modified** | `adapters/llms\|graphstores\|search/**` moved deny→ask; `.claude/rules/**` moved deny→ask; `adapters/auth/**` **kept deny** (no ADR-0005 capability assigned yet); `notes.tier_mapping` updated to explain the change |
| `.claude/rules/agentic_workflows.md` | **Modified (banner only)** | Added a superseded-by-ADR-0005 banner at the top. Full native-orchestration design spec (Coordinator/Planner/ToolUseAgent pseudocode) **retained, not deleted** — historical reference; full retirement decision is Lot 17 |
| `.claude/rules/agents.md` | **Modified (banner only)** | Same treatment — V1 interface patterns still valid and retained; V2+ native-coordination sections marked historical only |
| `.claude/rules/security-layers.md` | **Modified** | Deny/ask tables and folder-segmentation diagram synced with the settings.json change; CLAUDE.md-blocks table row for block 09 reworded; "Rationale" bullets updated |
| `.claude/rules/adapters.md` | **Modified** | `.gitkeep` stub table reworded (llms/graphstores = delegation targets, not version-gated stubs; auth unchanged); rule text clarified — these adapters call the external engine, not reimplement it |
| `.claude/rules/orchestration.md` | **Modified (light)** | One-line fix on `FlowCompiler`/"V2 agent orchestration"; §9 "V2 Orchestration (Future, Out of Scope)" reframed as "Delegated per ADR-0005" |
| `.claude/agents/orchestration-specialist.md` | **Modified** | "Multi-Agent Orchestration (V2+)" expertise section and its worked YAML example reframed as delegated/historical, not a native design target |
| `.claude/agents/security-specialist.md` | **Modified** | "Policy-based access control (V2+)" relabeled — this is owned/current per ADR-0005 §5.1, not deferred |
| `.claude/project-structure.md` | **Modified (footnote)** | Note added after the directory tree: `agents/` delegated, `memory/` KG data-model-vs-traversal split contingent on Lot 6, adapters status |
| `ROADMAP.md` | **Modified (banner only)** | Same superseding banner as `CLAUDE.md` §09 — full reconciliation stays Lot 17 scope per ADR-0005's own mitigation plan |
| `.claude/rules/contracts.md` | **Retained, untouched** | Protocol-change discipline — orthogonal to the ADR |
| `.claude/rules/security.md` | **Retained, untouched** | Safety/Security split, PII, risk scoring — all owned §5.1 material already |
| `.claude/rules/tests.md` | **Retained, untouched** | Test-scope rules — orthogonal |
| `src/modular_rag/security/CLAUDE.md` | **Retained, untouched** | Owned §5.1 material, no delegated-capability content |
| `src/modular_rag/contracts/CLAUDE.md` | **Retained, untouched** | Protocol discipline, reusable as-is for the future `DocumentEngine` port |
| `src/modular_rag/orchestration/CLAUDE.md` | **Retained, untouched (judgment call)** | One soft "`StateMachine`... V2+ feature" mention — read as describing the native adapter's own internal state handling, not competing scope. Revisit only if it causes real confusion later. |
| All 16 files under `.claude/skills/` | **Retained, untouched** | Pure QA/workflow mechanics (test running, layering checks, scaffolding) — zero references to delegated capabilities found |
| `.claude/hooks/post-edit-quality.ps1`, `.claude/layering-baseline.txt`, `.claude/AGENTS.md` | **Retained, untouched** | No roadmap/capability content |
| `.claude/settings.local.json` | **Out of scope, not read** | Personal, deliberately excluded per `CLAUDE.md` |
| `.claude/agents/retrieval-specialist.md` | **Retained, untouched** | "Embedding fine-tuning" mention judged ambiguous, not a real conflict with the delegated fine-tuning *platform* scope |
| `.claude/agents/ingestion-specialist.md`, `generation-specialist.md`, `test-specialist.md`, `architecture-reviewer.md`, `observability-expert.md` | **Retained, untouched** | No delegated-capability language found |

## What this lot did not do

- Did not rewrite `CLAUDE.md` block 09 or `ROADMAP.md` in full — both got a superseding banner
  only, per ADR-0005's own stated mitigation ("full consolidation in Lot 17").
- Did not delete `agentic_workflows.md` or `agents.md`'s native-design content — banners only,
  consistent with the plan's "add before move" migration principle
  (`docs/refactoring-plan.md` §8).
- Did not open `adapters/auth/**` — no ADR-0005 capability is assigned to it yet.

## Acceptance evidence

Per `docs/refactoring-plan.md` §6, Lot 2 row ("Shared Claude configuration matches ADR; quality
workflows retained; local settings untouched"):
- Every file identified by the pre-lot inventory as contradicting ADR-0005 §5.2 has been updated
  or explicitly deferred with a reason (table above).
- All 16 skills, the 3 orthogonal rule files, both module `CLAUDE.md` files with no
  delegated-capability content, and `.claude/settings.local.json` were left untouched.
- `.claude/settings.json` remains valid JSON after edits (verified).
