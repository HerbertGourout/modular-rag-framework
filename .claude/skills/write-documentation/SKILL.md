---
name: write-documentation
description: Create or rewrite one Markdown document by applying the repository documentation style guide, preserving every fact outside the explicitly authorized content corrections.
argument-hint: "<path> <create|form|content> <authorized scope; for content, the claims to correct>"
disable-model-invocation: true
---

# Write Documentation

Create or rewrite exactly one document named in `$ARGUMENTS`, applying
`docs/guides/documentation-style-guide.md`.

The style guide is the only source of writing rules. Read it; do not rely on a remembered copy,
and do not add rules of your own.

## 1. Load the rules and the target

1. Read `docs/guides/documentation-style-guide.md` in full.
2. For an existing document, read it in full, not only the sections to change.
3. Read the sources the document relies on for any capability, count, path, or command it
   states.
4. Identify the kind of change from `$ARGUMENTS` (style guide, section 2):
   - `create` — a new document;
   - `form` — a form change only; no fact may change;
   - `content` — authorized content corrections, limited to the claims `$ARGUMENTS` names, with
     any accompanying form change.
   If the kind is not stated, ask before editing.
5. Decide whether the target is a dated record (ADR, lot record, archive, dated audit,
   `CHANGELOG.md` entry). If it is, its decisions and dates never change. The only content
   changes allowed are the two named in style guide section 1 — a lifecycle status transition or
   a dated amendment note — and only when `$ARGUMENTS` explicitly authorizes them.

If the requested change goes beyond the authorized scope, stop and ask before editing.

## 2. Build the two inventories

Before editing an existing document, build two separate lists.

**Preserved facts** — every fact not named as an authorized correction (style guide, section 2):

- commit hashes, counts, dates, versions, and statuses;
- file paths, commands, flags, and configuration keys;
- quoted text and normative wording, including connecting words, and acceptance criteria;
- evidence and caveats attached to a claim.

**Authorized corrections** — for `content` only, one entry per claim named in `$ARGUMENTS`:

- location and current text;
- corrected text;
- evidence, found by checking the sources of truth in their order.

If a correction cannot be backed by evidence, do not apply it: report it in step 6. If you find a
claim that needs correcting but is not named in `$ARGUMENTS`, add it to the report, not to the
authorized list.

Keep both inventories for step 5.

## 3. Write

Apply the readability rules (style guide, section 3):

- choose the construct by content: paragraph for one idea, list for parallel items, table for a
  structured comparison, alert only for what a reader must not miss;
- metadata as a list; no multi-sentence table cells; no skipped heading levels;
- a table of contents when the document has more than about five `##` sections;
- context, current state, limits, actions, and references kept apart;
- prose wrapped at about 100 characters.

State capabilities only with the controlled vocabulary (style guide, section 4). Never present a
`planned` or `contract-only` capability as available.

New documents cite other files by section and quoted phrase, not by line number (rule b).

## 4. Verify what you wrote

- Every relative link and every cited path exists. Check each one with Glob or Read.
- Every anchor link matches a real heading.
- Every command, flag, and configuration key exists in the repository.
- Capability statements match their evidence. When in doubt, run `/verify-documentation-truth`
  on the document instead of guessing.

## 5. Check fidelity and references

1. Compare the new version with the preserved-facts inventory. Every preserved fact must still be
   present with the same value and wording.
2. Compare the new version with the authorized-corrections inventory. Each correction must appear
   exactly as recorded, and nothing else may have changed in content.
3. Rule (a): if lines moved in a file cited as `file:line` by
   `docs/onboarding-baseline-audit-2026-09-17.md`, search the audit for references to that file
   and update the line numbers in the same change.
4. Run `scripts/check_docs.py` and `git diff --check`.

## 6. Report

Report, in this order:

1. **Changed:** the document, the kind of change, and what was restructured.
2. **Fidelity:** confirmation that the preserved-facts inventory is intact, or each deviation
   with its reason.
3. **Authorized corrections:** each with location, text before, text after, and evidence; or
   "none" for `create` and `form`.
4. **References:** audit line references updated under rule (a), or "none affected".
5. **Defects not fixed:** content defects outside the authorized scope, and corrections that
   lacked evidence, each with location and evidence. Do not fix them in this change.
6. **Checks:** results of `check_docs.py` and `git diff --check`; the rendered view still needs a
   human look in the pull request preview.

Never commit or push. The human decides delivery.
