---
description: Run the bounded Claude Code to Codex delivery loop from implementation through final validation.
argument-hint: "<task, acceptance criteria, and intended file scope>"
disable-model-invocation: true
---

# Automated Delivery Loop

Run the complete bounded delivery workflow for `$ARGUMENTS`. The user invoking
this skill authorizes local checkpoint commits for the declared task paths, but
never a push, merge, tag, release, destructive cleanup, or unrelated commit.

## Non-negotiable behavior

- Read `CLAUDE.md`, `AGENTS.md`, and
  `docs/guides/ai-engineering-workflow.md` first.
- Claude Code is the sole implementation writer. Codex is read-only.
- Never include unrelated, pre-existing, personal, secret, or local-setting files
  in a checkpoint.
- Never stage `.env*`, `.claude/settings.local.json`, `.review/*`, or files outside
  the declared scope.
- Run at most two Codex passes. Pass 1 is discovery; pass 2 is closure only.
- `READY_FOR_FINAL_VALIDATION` ends the review loop immediately.
- Do not run integration/e2e checks unless their services and credentials are
  confirmed.
- Stop for human input only at an existing repository approval gate: destructive
  action, public contract/security-policy decision, new dependency, production
  manifest, unavailable required service, or an unresolved pass-2 BLOCKER/HIGH.

## 1. Establish the task boundary

From `$ARGUMENTS`, write down:

- one task statement;
- risk level (`LOW`, `NORMAL`, or `HIGH`);
- testable acceptance criteria;
- exact intended paths;
- out-of-scope work;
- required validations and unavailable external services.

Run `git status --short` and `git diff --cached --name-only`. If the index already
contains files outside the declared scope, stop rather than altering or committing
someone else's staged work. Record the starting commit as `BASE_SHA` with
`git rev-parse HEAD`.

For a low-risk docs-only or trivial test-only task, Codex review is optional per
`docs/guides/model-routing.md`; implement and validate directly unless the user
explicitly requested independent review.

## 2. Implement and self-review

Implement only the declared task. Add or update tests and documentation required
by the acceptance criteria. Run targeted checks, then self-review the complete
scoped diff for behavior, error paths, security, contracts, manifests, migrations,
and layering as applicable.

Create `.review/handoff.md` by running `scripts/prepare_review.ps1` with:

- the task and risk level;
- `-Base BASE_SHA`;
- `-ReviewPass 1`;
- every acceptance criterion;
- executed/unavailable validations;
- out-of-scope items;
- exact task paths.

Complete all semantic sections in the generated handoff. Do not leave placeholder
acceptance criteria.

## 3. Create the implementation checkpoint

Stage only the declared paths using an explicit path list. Re-check
`git diff --cached --name-only`; every staged path must belong to the task. Create
one local checkpoint commit and record it as `IMPLEMENTATION_SHA`. Do not push.

Refresh `.review/handoff.md` after the checkpoint so its generated Git context is
current. The original `BASE_SHA` remains the task base.

## 4. Run Codex pass 1 automatically

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_codex_review.ps1 `
  -Task "<task>" -ReviewPass 1
```

Read `.review/codex-review.md` completely.

- If status is `READY_FOR_FINAL_VALIDATION`, skip directly to step 7.
- If status is `CHANGES_REQUIRED`, continue once to remediation.
- The helper resolves Codex from `-CodexPath`, `CODEX_CLI_PATH`, `PATH`, then the
  VS Code/VS Code Insiders/Cursor extension bundles. If discovery still fails but
  an absolute executable path is known, retry once with `-CodexPath <path>`.
- If the helper reports that the discovered CLI is not authenticated, surface its
  exact one-time `login --device-auth` command. Do not attempt to bypass login or
  substitute a secret from repository files.
- If the report is malformed or Codex CLI/authentication remains unavailable,
  report the precondition failure; do not fabricate approval.

## 5. Remediate once, as one batch

Verify every finding independently. In `.review/handoff.md`, record each decision
as `FIXED`, `DEFERRED`, `ACCEPTED_RISK`, or `REJECTED`, with evidence.

Default disposition policy:

- fix every valid `BLOCKER` and `HIGH` in scope;
- fix a `MEDIUM` when it directly violates an acceptance criterion and remains a
  narrow change;
- defer unrelated/pre-existing `MEDIUM` and all non-material `LOW` findings;
- stop for human approval when fixing a finding crosses a repository approval
  gate or materially expands the task.

Apply all accepted fixes in one batch and rerun the relevant validations. Stage
only the declared paths, verify the staged inventory, create one local corrective
checkpoint commit, and record it as `CORRECTIVE_SHA`. Do not push.

Refresh the handoff with `scripts/prepare_review.ps1` using the original
`BASE_SHA`, `-ReviewPass 2`, `-CorrectiveBase IMPLEMENTATION_SHA`, and the same
task path list. Confirm the finding-resolution table was preserved.

## 6. Run Codex pass 2 automatically

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_codex_review.ps1 `
  -Task "<task>" -ReviewPass 2
```

This always ends the Codex loop. Never request a third general review. If a
`BLOCKER` or `HIGH` remains, stop and present the exact human decision required.

## 7. Final deterministic validation

Run `/qa-v1` or the smallest equivalent full local gate appropriate to the task.
Run integration, e2e, Docker, paid-LLM, or production checks only when their
prerequisites are confirmed. Do not reinterpret a skipped required check as a
pass.

Report only:

- final review status and number of Codex passes;
- checkpoint SHA(s);
- validations passed, failed, or unavailable;
- deferred/accepted risks;
- the exact remaining human action.

Do not push. The normal final human action is to inspect the result and explicitly
request the push.
