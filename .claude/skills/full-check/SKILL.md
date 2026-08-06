---
name: full-check
description: Run unit tests, contract conformance tests, and coverage before opening a pull request
---

# Full Check

Comprehensive local validation that mirrors most of `.github/workflows/ci.yml` (minus
integration/e2e, which need live services, and minus the separate `coverage` CI job, which this
script does not run).

## What to do

1. Run `./scripts/check.sh full` with the Bash tool.
2. Summarize the result for each of its 7 steps: ruff lint, `compileall`, layering audit
   (`check_layering.py --strict`), mypy (ratcheted against `.claude/mypy-baseline.txt`),
   runnable-manifest load check, unit test count (pass/fail), contract test count (pass/fail).
3. If anything failed, read the failing test, fix the root cause in `src/modular_rag/`, and re-run. Don't paper over a failing test by weakening the assertion.
4. This script does **not** measure coverage — that's a separate CI job (`coverage:` in
   `.github/workflows/ci.yml`). If you need a coverage number, run `pytest --cov=src/modular_rag`
   directly; see [docs/guides/adoption-metrics.md](../../../docs/guides/adoption-metrics.md) for
   the target (≥92%).

## Equivalent command

```bash
./scripts/check.sh full
# runs 7 steps, in order:
#   1. ruff check src/modular_rag/ tests/ --select E,F,I,N,W,UP,B,C4
#   2. python -m compileall -q src/modular_rag
#   3. python scripts/check_layering.py --strict
#   4. mypy src/modular_rag/ (error count must not exceed .claude/mypy-baseline.txt)
#   5. load_pipeline('manifests/presets/local-hybrid-rag.yaml') — confirms the one Runnable manifest still wires
#   6. pytest tests/unit/ -v
#   7. pytest tests/contract/ -v
```

## When to use

Before pushing a branch / opening a PR. For Qdrant-backed or LLM-backed scopes, use `pytest tests/integration -m integration` and `pytest tests/e2e -m e2e` directly (see CLAUDE.md block 06) — those require live services and aren't part of this skill.
