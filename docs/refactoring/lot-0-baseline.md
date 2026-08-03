# Lot 0 — Programme Control, Baseline Snapshot, Ownership, Change Policy

**Status:** IN PROGRESS
**Date recorded:** 2026-08-03
**Depends on:** none
**Gates:** Lot 1 (Product-boundary ADR)

This document is the Lot 0 deliverable required by
[docs/refactoring-plan.md](../refactoring-plan.md#9-revised-execution-order) section 11, Phase A: a reproducible
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

| Decision class | Authority | Notes |
|---|---|---|
| ADR approval (product boundary, engine selection, contracts) | Full team consensus (4) | One blocking objection holds the ADR at `Proposed`. |
| Lot acceptance (evidence sign-off per §12 of the plan) | Lot owner + one reviewer from the table below | Not the same person for both roles. |
| Plan-change (scope, order, lot content) | Same as ADR approval | Per `docs/refactoring-plan.md` line 14: only after a blocking discovery, a material scope change, or an approved architecture decision. |
| Destructive/irreversible action (tag, force-push, history rewrite, data purge) | Explicit, separate, written approval from the full team | Per plan §14 item 9-10. Never implied by lot acceptance. |

## 3. Ownership (per lot, Phase A–D)

Team: Herbert Gourout + 3 colleagues (4 total). Names/roles below are placeholders —
**fill in before treating this section as binding**; the rest of the document does not depend
on who is named here.

| Lot(s) | Phase | Owner | Reviewer |
|---|---|---|---|
| 0–1 | Control & ADR | Herbert Gourout | _TBD_ |
| 2–3 | Claude realignment / CI baseline | _TBD_ | _TBD_ |
| 4–5 | Characterization / capability truth | _TBD_ | _TBD_ |
| 6–7 | Engine spike / contracts | _TBD_ | _TBD_ |
| 8–10 | Native adapter / config / audit | _TBD_ | _TBD_ |
| 11–14 | Governance / lifecycle / quality / reliability | _TBD_ | _TBD_ |
| 15–16 | External adapter / hardening | _TBD_ | _TBD_ |
| 17–18 | Retirement / pilot / closure | _TBD_ | _TBD_ |

No formal RACI matrix beyond this table — a 4-person team does not need one. The owner is
accountable for the lot's acceptance evidence; the reviewer confirms it before status moves to
`COMPLETE` in `docs/refactoring-plan.md` §9.

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
