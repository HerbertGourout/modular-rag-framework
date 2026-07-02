# Codex Project Notes

Persistent Codex behavior for this repository lives in `AGENTS.md`.

This directory is intentionally minimal. Use it only for Codex-specific project
configuration that cannot live in `AGENTS.md` or `docs/guides/`.

Current policy:

- `AGENTS.md` defines Codex's durable role and operating rules.
- `docs/guides/ai-engineering-workflow.md` defines the Claude Code + Codex workflow.
- `docs/guides/model-routing.md` defines provider and model-tier routing.
- Do not duplicate Claude Code skills under `.codex/`.
- Keep Codex as reviewer/challenger by default unless the user explicitly asks it
  to implement.
