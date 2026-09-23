# Documentation Style Guide

- **Status:** Active
- **Applies to:** every Markdown document in this repository
- **Applies to writers:** humans, Claude Code, and Codex alike
- **Introduced by:** Batch 0.5 of
  [`docs/onboarding-overhaul-plan.md`](../onboarding-overhaul-plan.md)
- **Executed by:** `/write-documentation`, `/review-documentation-quality`,
  `/verify-documentation-truth` (in `.claude/skills/`)

## Contents

1. [Scope and precedence](#1-scope-and-precedence)
2. [Fidelity rules](#2-fidelity-rules)
3. [Readability rules](#3-readability-rules)
4. [Capability status vocabulary](#4-capability-status-vocabulary)
5. [References to other files](#5-references-to-other-files)
6. [Worked example](#6-worked-example)
7. [Checking a document](#7-checking-a-document)

---

## 1. Scope and precedence

This guide defines how documentation is written in this repository. The three documentation
skills execute it; they do not add rules of their own.

It applies in full to every document created from now on.

For existing documents, it applies when a task rewrites the document. Do not reformat unrelated
documents in passing: readability work follows the batches of the onboarding overhaul plan.

Dated records keep their decisions and dates as written:

- ADRs in `docs/adr/`;
- lot records in `docs/refactoring/`;
- `docs/archive/`;
- dated audits and `CHANGELOG.md` entries.

Their form may be corrected when a task touches them. Only two content changes are allowed, and
only when a task explicitly authorizes them:

- **a lifecycle status transition** that follows the record's own process — for example, an ADR
  moving to `Accepted` after approval, as `docs/adr/_index.md`, section "How to Propose an ADR",
  requires, or a record marked as superseded;
- **a dated amendment note** added next to the original text, which leaves the original decision
  unchanged.

When this guide conflicts with a source of truth listed in the plan's
[Sources of Truth](../onboarding-overhaul-plan.md#4-sources-of-truth) section, that source wins
on content. This guide governs form and the discipline of changing content; it never decides
what the content is.

## 2. Fidelity rules

These rules are non-negotiable. Readability never justifies breaking them.

A documentation change is one of two kinds, and the task states which:

- **Form change** — layout, structure, and wording discipline. No fact changes.
- **Authorized content correction** — the task names the specific claims to correct. Only those
  claims change, and each new value is verified against the sources of truth, in their order.

A task may combine both, as long as every content correction is named in its scope.

**A form change never changes a factual value.** Every fact outside the authorized corrections
stays verbatim:

- commit hashes, in full;
- counts, dates, versions, and statuses;
- file paths, commands, flags, and configuration keys;
- quoted text and normative wording, such as an authority order or an acceptance criterion,
  including its connecting words.

**Content is never changed silently.** Each authorized correction is recorded with its location,
the text before, the text after, and the evidence. A content defect found outside the authorized
scope is reported, not fixed in passing; it is then corrected as its own, explicitly authorized
change.

**Shortening is not summarizing.** Splitting a sentence, moving a list out of a table cell, or
adding a heading is allowed. Dropping a qualifier, a caveat, or a piece of evidence is not.

## 3. Readability rules

### 3.1 Paragraphs

- One paragraph holds one idea.
- A paragraph is usually two to four sentences.
- Separate paragraphs with a blank line.

Line breaks in the source do not create a line break in the rendered page. Consecutive lines
without a blank line between them render as one paragraph.

### 3.2 Lists

- Use a list for three or more parallel items.
- Use a numbered list only when order matters: steps, priority, or precedence.
- Leave a blank line before and after a list.

### 3.3 Metadata

Document metadata is a bulleted list, one field per item. Never write it as consecutive
`**Field:**` lines in one paragraph: GitHub renders them as a single block of text.

A field whose value runs to more than one sentence, or is itself a list, may instead become its
own labelled paragraph or list directly after the short fields.

### 3.4 Tables

- Use a table only for a structured comparison, where every row has the same fields.
- Keep each cell to a short phrase; no multi-sentence cells.
- Move long file lists out of cells, into a list or a numbered note under the table.
- When one column needs explanation per row, keep the table short and add a list below it.
- Leave a blank line before and after a table.

### 3.5 Headings and navigation

- Heading levels never skip: a `###` sits under a `##`.
- One `#` title per document.
- A document with more than about five `##` sections starts with a table of contents.
- Every entry in a table of contents is a working anchor link.

### 3.6 Source layout

- Wrap prose lines at about 100 characters. Table rows and URLs are exempt.
- Do not use `<br>` unless no Markdown construct can express the layout.
- Use GitHub alerts (`> [!NOTE]`, `> [!WARNING]`) sparingly, for information a reader must not
  miss.

### 3.7 Structure of a section

Keep these kinds of information apart, under their own heading or paragraph:

- **context** — why the subject matters;
- **current state** — what exists today, with evidence;
- **limits** — what does not exist, is partial, or is not verified;
- **actions** — what the reader or a later batch must do;
- **references** — where the detail lives.

## 4. Capability status vocabulary

Capability status uses the two-axis vocabulary defined in the Batch 0 audit, section
[2. Controlled vocabulary for capability states](../onboarding-baseline-audit-2026-09-17.md#2-controlled-vocabulary-for-capability-states):

- **availability:** `implemented`, `partial`, `contract-only`, `planned`;
- **ownership:** `native` (default, usually omitted) or `delegated`.

Refer to that section; do not redefine the terms differently.

Two rules apply everywhere:

- `delegated` never appears alone. Write `planned (delegated)`, never `delegated`.
- A `planned` or `contract-only` capability is never described as available, usable, or
  supported.

## 5. References to other files

### 5.1 Existing documents

The Batch 0 audit cites many findings as `file:line`. Line numbers move whenever a file above
them changes.

**Rule (a):** a change that shifts lines in a file cited by `file:line` in
`docs/onboarding-baseline-audit-2026-09-17.md` updates those references in the audit, in the same
change.

### 5.2 New documents

**Rule (b):** new documents cite a section heading plus a short quoted phrase, not a line number.

For example, write: `docs/glossary.md`, section "Assurance level", which says "An adapter cannot
assert its own level." Do not write `docs/glossary.md:278-286`.

That example is itself the reason for the rule. The section it cites used to be called "Assurance
level (proposed)" and used to say the levels were not implemented; Batch 8 corrected both. A
heading-plus-phrase citation survives an edit visibly — it stops matching, and the reader knows to
look. A line number goes silently wrong.

Line numbers remain acceptable in transient review artifacts, such as `.review/handoff.md` and
Codex reports, which describe one immutable commit.

## 6. Worked example

This is a form change. The header comes from the Batch 0 audit as merged at `5fb5c71`. Its source
looks orderly, but GitHub renders its six fields as one dense paragraph.

**Before** — all six fields, copied verbatim:

```markdown
**Date:** 2026-09-17 (revised the same day after Codex review pass 1)
**Batch:** [`docs/onboarding-overhaul-plan.md`](onboarding-overhaul-plan.md) — Batch 0
**Scope:** onboarding, architecture, development, testing, operations, Claude Code, Codex,
review, troubleshooting, and contribution documentation. Implementation, tests, manifests, and
CI workflows under `src/`, `tests/`, `manifests/`, `scripts/`, and `.github/workflows/` were read
only as verification evidence — none were modified.
**Immutable base:** `2150ce266da4b1e6b52dda9e8152ee97ec7d8cb4` (`main`)
**Authority order:** executable code, manifests, tests, CI, accepted ADRs and public contracts,
then `CLAUDE.md`/`AGENTS.md`/path-scoped rules, then `ROADMAP.md`/`docs/refactoring-plan.md`,
then guides and indexes, then Git history — per this plan's §4.
**Predecessor:** [`docs/documentation-alignment-audit-2026-08-12.md`](documentation-alignment-audit-2026-08-12.md),
a comparable audit already self-marked as a historical snapshot. Its findings predate Lots 20–22
and the current Claude Code guide set; this document supersedes it as the current baseline.
```

**After:**

```markdown
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
```

Field-by-field check:

| Field | Form change applied | Text |
|---|---|---|
| Date | List item | Unchanged |
| Batch | List item | Unchanged |
| Immutable base | List item, moved up to join the other short fields | Unchanged, hash in full |
| Scope | Own paragraph, split at a sentence boundary | Unchanged |
| Authority order | Numbered list, split before each `then` | Unchanged, connectors and punctuation kept |
| Predecessor | Own paragraph, split at a sentence boundary | Unchanged |

Every field keeps its exact text. The changes are line breaks, blank lines, and list markers,
plus one reordering: `Immutable base` moves before `Scope` so the three short fields form one
list, as section 3.3 allows. A version that drops `Predecessor`,
shortens the hash to `2150ce2`, or removes the `then` connectors would break the
[fidelity rules](#2-fidelity-rules), however readable it looks.

## 7. Checking a document

Before handing a document over for review:

1. Run `/review-documentation-quality` on the file or the diff, and apply the minimal fixes.
2. Run `/verify-documentation-truth` when the document states capabilities, counts, paths, or
   commands.
3. Run `scripts/check_docs.py` and `git diff --check`. The script also prints non-blocking style
   warnings for the deterministic rules of this guide; `--style-path <file>` lists them for one
   document.
4. Look at the rendered view: the GitHub pull request preview, or the Markdown preview in your
   editor (`Ctrl+Shift+V` in VS Code) as a local approximation.

`/verify-documentation-truth` is the writer's self-check. It never replaces Codex's independent
review, as defined in [`AGENTS.md`](../../AGENTS.md) and
[`ai-engineering-workflow.md`](ai-engineering-workflow.md).
