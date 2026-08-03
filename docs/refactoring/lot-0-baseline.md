# Lot 0 — Programme Control, Baseline Snapshot, Ownership, Change Policy

**Status:** IN PROGRESS
**Date recorded:** 2026-08-03
**Depends on:** none
**Gates:** Lot 1 (Product-boundary ADR)

This document is the Lot 0 deliverable required by
[docs/refactoring-plan.md](../refactoring-plan.md#4-execution-order-and-sizing) §5, Phase A: a reproducible
baseline snapshot, explicit decision authority, and the rules under which the plan itself may
change. It does not tag, push, or alter remote state — none of those require authorization
beyond what is recorded here.

---

## 1. Baseline snapshot

| Field | Value |
|---|---|
| Branch | `main` |
| Commit SHA | `47ea77f7fd34458e99191e61258e3f488a959835` |
| Commit date | 2026-07-27 |
| Repository | `github.com/HerbertGourout/modular-rag-framework` |
| Snapshot recorded | 2026-08-03 |

**Dirty-worktree exclusions at snapshot time** (not part of the baseline, tracked separately):

| Path | State | Disposition |
|---|---|---|
| `docs/_index.md` | Modified (+1 line) | Pre-existing edit, unrelated to this programme. Not reverted. |
| `docs/refactoring-plan.md` | Untracked | The plan this programme executes. Commit alongside Lot 0/1 artifacts. |

No other uncommitted state existed at snapshot time. Static compilation and strict layering
checks were last confirmed passing as of this commit (per `docs/refactoring-plan.md` §1);
dynamic test results (unit/contract/integration/e2e) are **not** re-verified by this document —
that is Lot 3's deliverable (reproducible environment + CI gates).

## 2. Decision authority

**Current state (2026-08-03): sole authority.** The team named in ADR-0005/§3 below is a target,
not yet assembled — only Herbert Gourout is active. No decision in this plan is gated on
sign-off from anyone else while that remains true. This table is revisited (and a
second-approver rule reinstated where it makes sense) once additional team members are actually
confirmed and onboarded — not before.

| Decision class | Authority | Notes |
|---|---|---|
| ADR approval (product boundary, engine selection, contracts) | Herbert Gourout, sole | No blocking-objection mechanism while there is one decision-maker. |
| Lot acceptance (evidence sign-off per §12 of the plan) | Herbert Gourout, self-accepted | Two-person owner/reviewer split is reinstated once a second team member is active. |
| Plan-change (scope, order, lot content) | Herbert Gourout, sole | Per `docs/refactoring-plan.md` line 14: only after a blocking discovery, a material scope change, or an approved architecture decision — the bar is about *why* the plan changes, not about collecting signatures. |
| Destructive/irreversible action (tag, force-push, history rewrite, data purge) | Herbert Gourout, with explicit written confirmation in the moment | Per plan §14 item 9-10. Still requires a deliberate separate confirmation, not silent inclusion in a routine commit — solo authority is not a reason to skip that pause. |

## 3. Ownership (per lot, Phase A–D)

Target team: Herbert Gourout + up to 3 colleagues, **not yet assembled**. Until someone else is
actually onboarded, every lot's owner and reviewer is Herbert Gourout alone — the table below is
not pretending otherwise with placeholder names.

| Lot(s) | Phase | Owner | Reviewer |
|---|---|---|---|
| 0–18 | All phases | Herbert Gourout | Herbert Gourout (self-review) |

Re-split this table by phase once a second person is confirmed — see §2. Until then, a formal
RACI or owner/reviewer split would just be documentation theater.

## 4. Evidence locations

| Evidence class | Location |
|---|---|
| Lot status and dependency tracking | `docs/refactoring-plan.md` §9 (tracker table) |
| ADRs | `docs/adr/000N-*.md` |
| Per-lot artifacts (this file's siblings) | `docs/refactoring/lot-N-*.md` |
| Test evidence | `tests/unit`, `tests/contract`, `tests/integration`, `tests/e2e` + CI run logs under `.github/workflows/` |
| Decision log | `docs/refactoring-plan.md` §"Decision log" |
| Change history | `docs/refactoring-plan.md` §"Change history" |

## 5. Plan-change rules

Unchanged from `docs/refactoring-plan.md` line 14: the plan may change only after a blocking
discovery, a material scope change, or an approved architecture decision — and any such change
is itself recorded in that document's decision log and change history, not silently edited in
place.

---

**Next:** Lot 1 — [ADR-0005: Document-AI Control Plane Product Boundary](../adr/0005-document-ai-control-plane-boundary.md).
