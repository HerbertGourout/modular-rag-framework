---
name: full-check
description: Run unit tests, contract conformance tests, and coverage before opening a pull request
---

# Full Check

Comprehensive local validation that mirrors the `lint` + `test-unit` + `test-contract` + `coverage` jobs of `.github/workflows/ci.yml` (minus integration/e2e, which need live services).

## What to do

1. Run `./scripts/check.sh full` with the Bash tool.
2. Summarize the result: quick checks, unit test count (pass/fail), contract test count (pass/fail), coverage percentage.
3. If anything failed, read the failing test, fix the root cause in `src/modular_rag/`, and re-run. Don't paper over a failing test by weakening the assertion.
4. If coverage dropped below the project's working baseline, say so explicitly rather than silently ignoring it — see [docs/guides/adoption-metrics.md](../../../docs/guides/adoption-metrics.md) for the target (≥92%).

## Equivalent command

```bash
./scripts/check.sh full
# runs: quick checks, then
#   pytest tests/unit/ -v
#   pytest tests/contract/ -v
```

## When to use

Before pushing a branch / opening a PR. For Qdrant-backed or LLM-backed scopes, use `pytest tests/integration -m integration` and `pytest tests/e2e -m e2e` directly (see CLAUDE.md block 06) — those require live services and aren't part of this skill.
