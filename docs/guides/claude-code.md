# Claude Code Guide

This repository includes project-level Claude Code configuration to make day-to-day
development safer and more repeatable.

## Which Claude Code guide to read

Four guides cover Claude Code on this project. They are not alternatives: each answers a
different question, and this table is the declared order. When two disagree, the one higher in
this list wins, and root `CLAUDE.md` outranks all four.

| Read | When | It answers |
|---|---|---|
| [onboarding-claude-code.md](onboarding-claude-code.md) | Your first session on this project | Install, authenticate, run one bounded first task |
| **This guide** | You need to know what is configured here | Files, permissions, hooks, skills, and the maintenance rule |
| [claude-code-complete-development-guide.md](claude-code-complete-development-guide.md) | You are implementing a change | The day-to-day workflow, with worked examples |
| [CLAUDE-CODE-COMPLETE-GUIDE.md](CLAUDE-CODE-COMPLETE-GUIDE.md) | You are looking at governance or a configuration topic in depth | The governance-level hub and the reference-guide index |

The remaining `claude-code-*.md` files are reference material for one topic each. None is a
starting point, and most describe Claude Code in general rather than this repository's setup:

| Guide | Scope |
|---|---|
| [claude-code-settings-reference.md](claude-code-settings-reference.md) | General Claude Code settings reference; the settings this project actually sets are in `.claude/settings.json` and described below |
| [claude-code-advanced-config.md](claude-code-advanced-config.md) | General reference for subagents, skills, rules and hooks; not a description of this repository's configuration |
| [claude-code-plugins-marketplaces.md](claude-code-plugins-marketplaces.md) | General plugin and marketplace reference; this project defines no plugin or marketplace |
| [claude-code-mcp-setup.md](claude-code-mcp-setup.md) | General MCP reference; self-declared generic, and no `.mcp.json` exists here |
| [claude-code-enterprise-deployment.md](claude-code-enterprise-deployment.md) | Organization-wide deployment; self-declared as not configured in this project |

Treat a statement in those files as describing this repository only when this guide,
`.claude/settings.json` or a rule file confirms it.

For the delivery workflow with Codex, the authority is
[ai-engineering-workflow.md](ai-engineering-workflow.md) and [`AGENTS.md`](../../AGENTS.md), not
these guides.

## Files and Responsibilities

| Path | Role |
|---|---|
| `CLAUDE.md` | Main project memory: purpose, architecture rules, commands, workflow rules. |
| `.claude/.instructions.md` | Imported by `CLAUDE.md` into every session: layering rules, wiring pattern, observability signals, product boundary. |
| `.claude/.prompt.md` | Imported by `CLAUDE.md` into every session: response style and expected answer structure. |
| `.claude/settings.json` | Shared Claude Code settings for the repository. |
| `.claude/hooks/post-edit-quality.ps1` | Fast post-edit Ruff check used by the shared hook. |
| `.claude/skills/*/SKILL.md` | Project workflows exposed as slash commands. |
| `.claude/rules/*.md` | Path-specific guidance for contracts, security, and tests. |
| `CLAUDE.local.example.md` | Template for personal preferences. |
| `CLAUDE.local.md` | Optional personal file, ignored by Git. |
| `.claude/settings.local.json` | Optional local permissions, ignored by Git through the user's global Git ignore. |

### Approving a command rewrites the shared settings file

When you approve a command in Claude Code, the scope you pick decides which file records it.
**Approving at project scope rewrites `.claude/settings.json`**, the file everyone shares: the
command is appended to `permissions.allow`, so it is auto-approved for every contributor who
pulls the change, and the `description` field of `hooks.PostToolUse[0]` is dropped in the
rewrite.

This is a mechanism, not a bug to report, and it recurred repeatedly during the documentation
work of 2026-09. Three consequences follow:

- **Approve at local scope** unless the whole team should inherit the grant. Local grants land in
  `.claude/settings.local.json`, which is ignored by Git.
- **Check `git diff -- .claude/settings.json` before committing.** An unexpected diff there is
  almost always an approval that leaked into the shared file.
- **Restore the hook description** if it disappeared, and move the grant to the local file. Doing
  this as the last action of a session avoids a later approval reintroducing it.

A grant that genuinely belongs to the team is a deliberate change: add it in its own commit, with
the reason, rather than letting an approval prompt write it silently.

### Two different files are called `AGENTS.md`

They are unrelated, and "read AGENTS.md" is ambiguous unless the path is given:

| Path | Subject | Audience |
|---|---|---|
| [`AGENTS.md`](../../AGENTS.md) (repository root) | Codex's reviewer role and operating rules | Codex, and anyone preparing a review |
| [`.claude/AGENTS.md`](../../.claude/AGENTS.md) | The catalogue of the eight Claude Code subagents | Claude Code users |

Neither is a rename candidate: the root file's name is the convention Codex looks for, and the
`.claude/` one sits beside the `agents/` directory it describes. Always cite the full path.

### What every session actually loads

`CLAUDE.md` starts with `@.claude/.instructions.md` and `@.claude/.prompt.md`, so those two files
are part of every session's instructions, not optional reading. A path-scoped file in
`.claude/rules/` loads when a matching file is opened, and a module's own `CLAUDE.md` applies
inside that module.

That makes them a place where status drift is expensive: a stale sentence there reaches every
session. When an instruction file disagrees with the code, the code wins, and the instruction is
corrected in its own change — the same rule the onboarding guide states for documentation.

Claude Code skills are used instead of legacy `.claude/commands/` because current
Claude Code documentation treats skills as the recommended form for custom commands.
Project skills under `.claude/skills/<name>/SKILL.md` are invoked with `/<name>`.

Official references:

- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks
- Settings: https://code.claude.com/docs/en/settings
- Project memory: https://code.claude.com/docs/en/memory

## Available Workflows

`.claude/skills/` currently holds 22 skills, not just the 5 validation-tier ones — the table
below is the complete list (a previous version of this table stopped at 5, which undersold what's
actually invokable):

| Command | Purpose | External services |
|---|---|---|
| `/test-unit` | Runs `pytest tests/unit`. | No |
| `/test-contract` | Runs `pytest tests/contract`. | No |
| `/qa-v1` | Runs Ruff, unit tests, contract tests, and layering audit. | No |
| `/delivery-loop` | Runs the bounded Claude writer → Codex reviewer loop, applies one correction batch when required, and finishes with deterministic validation. Never pushes. | Codex CLI; task-specific services only when confirmed |
| `/check-layering` | Runs `python scripts/check_layering.py`. | No |
| `/quick-check` | Fast syntax/import validation (ruff E,F,I), under 30s. | No |
| `/full-check` | Lint/compile/layering/type/manifest checks plus unit + contract tests; no coverage. | No |
| `/release` | Pre-tag validation: full + integration + e2e, CHANGELOG/version checks. | Qdrant + PostgreSQL + LLM key for the complete set |
| `/run-simple-qa` | Runs the bundled example ingest + ask flow. | Qdrant + LLM key |
| `/validate-security` | Manual 7-layer-defense checklist (secrets, cross-domain imports, direct wiring, lazy imports, PII patterns) — no CI job covers this yet. | No |
| `/validate-architecture` | Hexagonal layering, imports, and design-pattern validation. | No |
| `/add-component` | Scaffold a new contract-backed component (chunker, meter, embedder, indexer adapter) with implementation + unit + contract tests. | No |
| `/add-retriever` | Step-by-step workflow for a new `Retriever` implementation. | No |
| `/add-generator` | Step-by-step workflow for a new `Generator` implementation. | No |
| `/add-security-guard` | Step-by-step workflow for a new guard/filter/detector/policy. | No |
| `/design-retriever-fusion` | Tune or extend retriever fusion (vector + lexical + other). | No |
| `/optimize-chunking` | Analyze and optimize document chunking for retrieval quality. | No |
| `/prepare-evaluation` | Create evaluation datasets, metrics, and test scenarios. | No |
| `/parallel-feature-analysis` | Parallel analysis across retrieval/generation/security features. | No |
| `/write-documentation` | Create or rewrite one document by applying [the documentation style guide](documentation-style-guide.md): form changes preserve every fact; content corrections change only the claims the task names. | No |
| `/review-documentation-quality` | Read-only review of document form (`--file`, `--diff`, `--onboarding`); proposes minimal fixes. | No |
| `/verify-documentation-truth` | Read-only check of documented claims against code, manifests, tests, CI, and ADRs; Claude Code's pre-handoff self-check, never a substitute for Codex review. | No |

Use `/qa-v1` before opening a GitHub PR. Use `/run-simple-qa` or `/release` only when Qdrant is
available on `localhost:6333` and the required LLM API key is set.

When pairing Claude Code with Codex, the preferred entrypoint is one command:

```text
/delivery-loop <goal, acceptance criteria, and intended file scope>
```

Claude Code remains the writer and invokes Codex non-interactively in a read-only sandbox. The
skill performs at most two Codex passes, stops immediately at `READY_FOR_FINAL_VALIDATION`, and
never pushes.

Codex discovery does not rely only on Claude's sandboxed `PATH`:
- The helper also detects the executable bundled by the VS Code/VS Code Insiders/Cursor
  extension, or accepts `CODEX_CLI_PATH`/`-CodexPath`.
- It verifies the CLI's own saved authentication before starting a review — chat/IDE login alone
  may not initialize CLI login.

The full workflow is documented in [AI engineering workflow](ai-engineering-workflow.md) and
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
