---
name: review-documentation-quality
description: Review the form of Markdown documents against the documentation style guide and propose minimal fixes, without changing content.
argument-hint: "--file <path> | --diff | --onboarding"
disable-model-invocation: false
---

# Review Documentation Quality

Review the **form** of Markdown documents against `docs/guides/documentation-style-guide.md`,
and propose the smallest fix for each problem.

This review is read-only. It does not edit files unless the user explicitly asks to apply the
proposed fixes. It never judges or changes technical content: factual accuracy belongs to
`/verify-documentation-truth`.

## 1. Select the documents

Read `$ARGUMENTS`:

- `--file <path>` — that one document.
- `--diff` — every Markdown file changed on the current branch, including untracked ones:
  - base: the base commit recorded in `.review/handoff.md` when it exists, otherwise
    `git merge-base HEAD main`;
  - tracked: `git diff --name-only <base> -- "*.md"`;
  - untracked: `git ls-files --others --exclude-standard -- "*.md"`.
  Use this mode before preparing a Codex handoff.
- `--onboarding` — the documents listed in section "3.1 Primary entry points and indexes" of
  `docs/onboarding-baseline-audit-2026-09-17.md`.

With no argument, ask which mode to use.

## 2. Load the rules

Read `docs/guides/documentation-style-guide.md` in full. Every finding must name the style-guide
section it applies.

## 3. Check each document

Read each document in full. Look for:

| Problem | How to detect it | Style guide |
|---|---|---|
| Merged metadata | Two or more `**Field:**` lines with no blank line between them | 3.3 |
| Long paragraph | More than about four sentences, or several ideas in one paragraph | 3.1 |
| Missing list | Three or more parallel items written inline in a sentence | 3.2 |
| Wide or dense table | Multi-sentence cells, file lists inside cells, rows far beyond screen width | 3.4 |
| Heading level skip | A heading more than one level below the previous one; more than one `#` | 3.5 |
| Missing contents | More than about five `##` sections and no table of contents | 3.5 |
| Broken navigation | A contents entry or anchor link that matches no heading | 3.5 |
| Markdown spacing | No blank line before or after a list or table | 3.2, 3.4 |
| Long source lines | Prose lines well beyond 100 characters | 3.6 |
| `<br>` tags | Any `<br>` where a list or paragraph would work | 3.6 |
| Mixed section roles | Context, current state, limits, and actions blended in one block | 3.7 |
| Repetition | The same explanation repeated across sections of the document | 3.1 |

Classify each finding:

- **must-fix** — the rendered page is broken or misleading: merged metadata, a split or broken
  table, a heading skip, a dead anchor;
- **should-fix** — the page renders but is hard to read.

If a proposed fix would require changing a fact, a status, or normative wording, do not propose
it. Record it under "content concerns" instead (style guide, section 2).

## 4. Report

For each document, list findings as:

```text
<path>:<line> — <must-fix|should-fix> — <problem> (style guide <section>)
  Minimal fix: <the smallest change that resolves it>
```

Line numbers are acceptable here: this report describes one working tree (style guide,
section 5.2).

End with:

1. counts of must-fix and should-fix findings per document;
2. **content concerns** noticed but out of scope, for `/verify-documentation-truth`;
3. a reminder that the rendered view still needs a human look in the pull request preview.
