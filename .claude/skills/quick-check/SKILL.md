---
name: quick-check
description: Run fast syntax and import validation (ruff E,F,I) after a code edit, in under 30 seconds
---

# Quick Check

Fast feedback loop for use after every code change, before committing.

## What to do

1. Run `./scripts/check.sh quick` with the Bash tool.
2. Report the result to the user in 1-3 lines: pass/fail, and if it failed, the file:line and rule code (E/F/I) for each violation.
3. If it failed, fix the violation yourself (it's almost always a missing import, an unused import, or import ordering) and re-run once to confirm it's clean. Don't re-run in a loop more than twice without explaining what's still failing.

## Equivalent command

```bash
./scripts/check.sh quick
# same as: ruff check src/modular_rag/ tests/ --select E,F,I
```

## Checks covered

- **E** — syntax errors (indentation, duplicate keys)
- **F** — undefined names (missing imports, typos)
- **I** — import order (alphabetical, grouped by type)

This does not run tests — use the `full-check` skill before opening an MR.
