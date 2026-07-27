# Claude Code Guide

This repository includes project-level Claude Code configuration to make day-to-day
development safer and more repeatable.

## Files and Responsibilities

| Path | Role |
|---|---|
| `CLAUDE.md` | Main project memory: purpose, architecture rules, commands, workflow rules. |
| `.claude/settings.json` | Shared Claude Code settings for the repository. |
| `.claude/hooks/post-edit-quality.ps1` | Fast post-edit Ruff check used by the shared hook. |
| `.claude/skills/*/SKILL.md` | Project workflows exposed as slash commands. |
| `.claude/rules/*.md` | Path-specific guidance for contracts, security, and tests. |
| `CLAUDE.local.example.md` | Template for personal preferences. |
| `CLAUDE.local.md` | Optional personal file, ignored by Git. |
| `.claude/settings.local.json` | Optional local permissions, ignored by Git through the user's global Git ignore. |

Claude Code skills are used instead of legacy `.claude/commands/` because current
Claude Code documentation treats skills as the recommended form for custom commands.
Project skills under `.claude/skills/<name>/SKILL.md` are invoked with `/<name>`.

Official references:

- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks
- Settings: https://code.claude.com/docs/en/settings
- Project memory: https://code.claude.com/docs/en/memory

## Available Workflows

| Command | Purpose | External services |
|---|---|---|
| `/test-unit` | Runs `pytest tests/unit`. | No |
| `/test-contract` | Runs `pytest tests/contract`. | No |
| `/qa-v1` | Runs Ruff, unit tests, contract tests, and layering audit. | No |
| `/check-layering` | Runs `python scripts/check_layering.py`. | No |
| `/run-simple-qa` | Runs the bundled example ingest + ask flow. | Qdrant + LLM key |

Use `/qa-v1` before opening a GitHub PR. Use `/run-simple-qa` only when Qdrant is
available on `localhost:6333` and the required LLM API key is set.

When pairing Claude Code with Codex, keep Claude Code as the default writer and use
Codex for independent review. The full workflow is documented in
[AI engineering workflow](ai-engineering-workflow.md) and
[Model routing](model-routing.md).

## Post-Edit Hook

After Claude Code edits or writes a file, `.claude/settings.json` runs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .claude/hooks/post-edit-quality.ps1
```

The script prefers `.venv\Scripts\ruff.exe` when present, falls back to `ruff` on
the `PATH`, and checks only fast import/style failures:

```powershell
ruff check src/modular_rag tests --select E,F,I --quiet
```

This hook is intentionally lightweight. It should catch obvious syntax, import, and
formatting regressions without turning every edit into a full test run.

## Layering Audit

The repository's architecture depends on strict import boundaries. Run:

```powershell
python scripts/check_layering.py
```

The checker parses Python imports and reports violations for:

- `core/` importing outside `core/`.
- `contracts/` importing outside `core/` or `contracts/`.
- `adapters/` importing domain modules.
- domain modules importing other domain modules.

By default, the checker accepts entries listed in `.claude/layering-baseline.txt`
and fails only on new violations. To inspect all known debt, run:

```powershell
python scripts/check_layering.py --strict --show-baseline
```

The checker is diagnostic. A reported violation should usually be fixed by moving
shared types into `core/models/`, adding or updating a `contracts/` Protocol, or
wiring through `orchestration/` instead of importing across domains.

## Local Personalization

For personal preferences, copy the example file:

```powershell
Copy-Item CLAUDE.local.example.md CLAUDE.local.md
```

Keep machine-specific values out of Git:

- API keys.
- Local Qdrant URLs.
- Private endpoint names.
- Personal command permissions.

`CLAUDE.local.md` is ignored by the repository `.gitignore`.

## Maintenance Checklist

When the project changes, update Claude Code configuration in the same MR:

1. New development workflow: add or update a skill in `.claude/skills/`.
2. New architectural boundary: update `CLAUDE.md`, docs, and the layering checker.
3. New required local service: update `CLAUDE.local.example.md`.
4. New test category: update `/qa-v1` and this guide.
5. New path-specific convention: add or update `.claude/rules/`.
