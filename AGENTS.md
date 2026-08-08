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

Use one writer and one or more reviewers:

1. Claude Code builds the change using `CLAUDE.md` and `.claude/skills/`.
2. Claude Code runs `/qa-v1` when the local environment is ready.
3. Codex reviews the Git diff independently.
4. Codex reports only material findings: bugs, regressions, missing tests,
   security risks, manifest issues, and architecture violations.
5. A human decides which findings become changes.

Codex may implement targeted fixes only after the review findings are accepted or
the user asks Codex to continue as the writer.

## Review Prompt

Use this stance by default for reviews:

```text
Review the current Git diff as an independent staff engineer.
Prioritize bugs, regressions, security issues, contract breaks, manifest wiring
issues, tests missing for changed behavior, and layering violations.
Ignore cosmetic style unless it causes a defect.
Do not modify files unless explicitly asked.
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
