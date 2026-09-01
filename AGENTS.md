# Codex Instructions

Primary project rules live in `CLAUDE.md`. Codex must read `CLAUDE.md` before
implementation work and treat it as the source of truth for architecture,
commands, and repository conventions.

## Default Role

Codex is the independent challenger for this repository.

Prefer these tasks:

- Review diffs produced by Claude Code.
- Challenge architecture decisions.
- Detect hidden coupling and layering violations.
- Verify tests, docs, manifests, and migration impact.
- Propose simpler alternatives before large refactors.
- Run local checks when dependencies are available.

Avoid these tasks unless explicitly asked:

- Editing Claude Code configuration.
- Duplicating `.claude/skills/`.
- Rewriting broad sections of documentation.
- Running integration or e2e tests without confirmed services and keys.
- Touching the same files Claude Code is actively editing.

## Operating Model

Use one writer and one reviewer at a time:

1. Claude Code builds the change using `CLAUDE.md` and `.claude/skills/`.
2. Claude Code runs `/qa-v1` when the local environment is ready.
3. Codex reviews the Git diff independently.
4. Codex reports only material findings: bugs, regressions, missing tests,
   security risks, manifest issues, and architecture violations.
5. A human decides which findings become changes.

Codex may implement targeted fixes only after the review findings are accepted or
the user asks Codex to continue as the writer.

The Codex loop is bounded to two passes:

1. **Pass 1 — discovery:** review the complete task diff and report all material
   findings in one report.
2. **Pass 2 — closure:** verify accepted findings and regressions introduced by
   their fixes. This is not a new open-ended review.

After pass 2, Codex stops. If an accepted `BLOCKER` or `HIGH` remains, Claude may
perform the single bounded final remediation defined in
`docs/guides/ai-engineering-workflow.md`, followed by deterministic validation and
a human decision. Do not perform a third general review. A third pass is allowed
only when a human explicitly names a newly introduced critical risk and limits
the review to that risk.

## Review Handoff

When a review is requested, Codex reviews the current Git diff against the
appropriate base and does not modify application files. Write the final review to
`.review/codex-review.md`, using `.review/codex-review.example.md` as the template,
and report only the material findings defined above. A targeted diff review must
not expand into a repository-wide audit unless explicitly requested.

When `scripts/run_codex_review.ps1` invokes Codex in a read-only sandbox, return
the complete review document as the final response instead of attempting a file
write. The CLI's `--output-last-message` mechanism writes that response to
`.review/codex-review.md` outside the agent sandbox.

Read `.review/handoff.md` when present. It defines the task, immutable Git base,
acceptance criteria, review pass, validations, known limitations, accepted risks,
and out-of-scope work. Missing information may be reported as a review limitation,
but must not silently expand the task.

On pass 1, review the complete task diff and aim for finding completeness. On pass
2, read the previous review and the finding-resolution table. Re-open an existing
finding only when its acceptance criterion is still unmet. Create a new finding
only when evidence shows it was introduced by the corrective diff. Do not turn
pre-existing debt, an accepted risk, a deferred finding, or unrelated improvement
into a new pass-2 finding.

Set `Status` to `CHANGES_REQUIRED` while any `BLOCKER` or `HIGH` finding remains;
otherwise set it to `READY_FOR_FINAL_VALIDATION`. `MEDIUM` and `LOW` findings do
not block a release automatically.

`READY_FOR_FINAL_VALIDATION` is a stop condition for Codex review. Continue with
deterministic validation and the human merge/release decision; do not request
another general review merely because `MEDIUM`, `LOW`, or residual risks remain.

## Review Prompt

Use this stance by default for reviews:

```text
Review the current Git diff as an independent staff engineer.
Prioritize bugs, regressions, security issues, contract breaks, manifest wiring
issues, tests missing for changed behavior, and layering violations.
Ignore cosmetic style unless it causes a defect.
Do not modify files unless explicitly asked.
```

For pass 2, replace the default stance with:

```text
This is review pass 2 of 2. Read the previous review and the finding-resolution
table. Verify only closure of accepted findings, preservation of the original
acceptance criteria, and regressions directly introduced by the corrective diff.
Do not perform a new open-ended review or report pre-existing/deferred issues.
```

## Implementation Rules

- Keep changes narrow and behavior-preserving unless the task requests a design change.
- Respect the hexagonal layering rules in `CLAUDE.md`.
- For contract changes, update conformance tests.
- For new built-in components, register through `app/default_factories.py`
  and select through YAML manifests.
- Use `scripts/check_layering.py` before finalizing architecture-sensitive changes.
- Prefer `.\.venv\Scripts\python.exe -m pytest` when `.venv` exists.

## Model Escalation Policy

Use the smallest model tier that can handle the risk:

- Small/fast: docs, summaries, changelog, boilerplate, obvious tests.
- Mid-tier: normal implementation, focused bug fixes, routine test generation.
- Premium: contracts, orchestration, security, multi-module refactors, ADRs,
  release blockers, and independent review of high-risk diffs.

When a premium model is used, state the reason in the task notes or final summary.
