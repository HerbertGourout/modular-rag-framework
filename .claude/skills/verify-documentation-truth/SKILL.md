---
name: verify-documentation-truth
description: Verify the technical claims of Markdown documents against code, manifests, tests, CI, ADRs, and project instructions before a Codex handoff.
argument-hint: "--file <path> | --diff"
disable-model-invocation: false
---

# Verify Documentation Truth

Check that what documents **state** is true in the repository: capabilities, counts, paths,
commands, configuration, and cross-document consistency.

This skill is Claude Code's **pre-handoff self-check**. Its result is recorded in
`.review/handoff.md`. It never replaces Codex's independent review defined in `AGENTS.md` and
`docs/guides/ai-engineering-workflow.md`, and a clean result is not an approval.

It is read-only. It reports findings; it does not correct documents. Form and layout belong to
`/review-documentation-quality`.

## 1. Select the documents

Read `$ARGUMENTS`:

- `--file <path>` — that one document.
- `--diff` — every Markdown file changed on the current branch, including untracked ones, using
  the same base selection as `/review-documentation-quality --diff`.

With no argument, ask which mode to use.

## 2. Extract the claims

Read each document in full and list every checkable claim:

- capability status: implemented, partial, contract-only, planned, delegated;
- counts: ADRs and their statuses, skills, subagents, presets, tests, lots;
- paths, files, and directories said to exist or not to exist;
- commands, CLI subcommands, script flags, and slash commands;
- manifest fields, component types, adapters, and engines said to be selectable;
- statements about what another document says or decides.

Skip claims inside dated records that were true at their date (ADRs, lot records, archive,
dated audits, `CHANGELOG.md` entries). A dated record is only a defect when it presents itself as
current.

## 3. Check each claim against evidence

Search in this authority order and stop at the highest source that settles the claim:

1. code, manifests, tests, and CI workflows;
2. accepted ADRs and public contracts;
3. `CLAUDE.md`, `AGENTS.md`, path-scoped rules, and checked-in tool configuration;
4. `ROADMAP.md` and `docs/refactoring-plan.md`;
5. guides and indexes.

Useful evidence locations:

| Claim | Where to check |
|---|---|
| A component type is selectable | Registration in `src/modular_rag/app/default_factories.py` |
| An engine is selectable | `load_engine()` in `src/modular_rag/app/bootstrap.py` |
| A contract exists | `src/modular_rag/contracts/` and its `__init__.py` exports |
| An adapter exists | `src/modular_rag/adapters/` |
| A manifest field exists | `src/modular_rag/contracts/manifests.py` |
| A preset is runnable | `manifests/presets/` and `manifests/README.md` |
| An ADR status | The status line in each `docs/adr/NNNN-*.md` header |
| A skill count | `.claude/skills/*/SKILL.md` |
| A CI job exists | `.github/workflows/*.yml` |
| A CLI command exists | `src/modular_rag/cli/` |

Apply the capability vocabulary of `docs/guides/documentation-style-guide.md`, section 4. In
particular:

- a capability described as available must pass the `implemented` or `partial` test;
- a capability with only a contract is `contract-only`, never available;
- `delegated` alone is itself a finding.

## 4. Classify

Give each claim one verdict:

- **CONTRADICTED** — evidence shows the claim is false;
- **UNVERIFIED** — no evidence either way was found;
- **CONFIRMED** — evidence supports the claim. List these only as a count, unless asked.

Typical contradictions:

- a planned capability presented as available;
- an implemented capability still described as future;
- a stale count;
- a command, path, or flag that no longer exists;
- an adapter or manifest value described as selectable when it is not;
- two current documents stating different things.

## 5. Report

For each CONTRADICTED or UNVERIFIED claim:

```text
<path>:<line> — <CONTRADICTED|UNVERIFIED>
  Claim: "<exact quoted text>"
  Evidence: <source path and what it shows, or where you searched>
  Minimal correction: <suggested wording, without applying it>
```

End with:

1. per document: confirmed, contradicted, and unverified counts;
2. the search method and its limit, when claims were located by search rather than a full read;
3. the text to copy into the "Validation → Executed" section of `.review/handoff.md`.

Do not edit documents from this skill. Corrections are made as an explicit change, then reviewed
by Codex.
