---
name: release
description: Pre-release validation — full + integration + e2e checks, CHANGELOG and version bump verification, before tagging a release
---

# Release

Pre-tag validation. Heavier than `full-check`: includes integration/e2e (needs Qdrant + LLM key) and release-hygiene checks that `scripts/check.sh` doesn't cover.

## Steps

1. **Pre-checks**: confirm on `main`, working directory clean (`git status`), up to date with `origin/main`.
2. **Run validation**: `./scripts/check.sh all` (quick + full + integration + e2e). Integration needs Qdrant on `localhost:6333`; e2e needs `OPENAI_API_KEY` (the SDK's own standard var, not `MRAG_OPENAI_API_KEY`) set. If either service isn't available, say so explicitly rather than silently skipping.
3. **CHANGELOG.md**: confirm it has an entry for this release (read the file, check the top section matches the changes being shipped).
4. **Version bump**: check `pyproject.toml` `version = "..."` was bumped relative to the last tag (`git tag --sort=-v:refname | head -1`).
5. **ADR check**: if this release includes a new top-level module, a new layer boundary, or a contract change, confirm a new file exists under `docs/adr/` (CLAUDE.md rule 07 — "ADR before structural changes").

## Report format

```
✓/✗ Branch is main, clean, up to date
✓/✗ ./scripts/check.sh all (quick/full/integration/e2e breakdown)
✓/✗ CHANGELOG.md updated
✓/✗ Version bumped (X.Y.Z -> X.Y.Z+1)
✓/✗ ADR present (if structural change)
```

Don't report "ready for release" unless every line is ✓ — if integration/e2e can't run because services aren't available, report that as a blocker, not a pass.
