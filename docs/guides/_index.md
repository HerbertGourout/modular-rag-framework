# Guides — Modular RAG Framework

**Rewritten 2026-08-06** (documentation audit, `docs/archive/documentation-audit-2026-08.md`) — the
previous version of this index was dated June 2026, carried internally-contradictory
"Updated" dates, and duplicated `docs/_index.md`'s navigation role without staying in sync with
it. This version follows `docs/_index.md`'s own terser, by-intent format.

**Joining the project?** Start at [docs/onboarding.md](../onboarding.md), the repository's entry
point; it says which of these guides to read, and when.

This directory holds two genuinely different kinds of guide — **framework guides** (how to run,
extend, deploy this RAG framework) and **Claude Code tooling guides** (how to use Claude Code
itself on this repository). They aren't physically separated into different folders (that would
break every existing link into this directory), but the tables below keep them apart.

---

## Framework guides — by intent

| You want to... | Go to |
|---|---|
| Work through a structured first week, with exercises and evidence | [first-week.md](first-week.md) |
| Run the framework for the first time | [getting-started.md](getting-started.md) |
| Install dependencies and configure the environment | [installation.md](installation.md) |
| Add a new component (chunker, retriever, generator...) | [plugin-development.md](plugin-development.md) |
| Deploy to production (container, manifest, hardening) | [deployment.md](deployment.md) |
| Back up, restore, or roll back a deployment | [backup-restore.md](backup-restore.md) |
| Read or wire up trace telemetry, live spans or operational metrics | [observability.md](observability.md) |
| Run the offline golden-set benchmark, or tune its quality-gate thresholds | [offline-evaluation.md](offline-evaluation.md) |
| Collect user feedback, run human review, or check for quality drift | [feedback-and-drift.md](feedback-and-drift.md) |
| Run the local/CI validation tiers, or debug a failing check | [validation-protocol.md](validation-protocol.md) |
| Fix a common error (Qdrant unreachable, RegistryError, layering violation...) | [troubleshooting.md](troubleshooting.md) |
| Understand the Claude Code / Codex two-provider review workflow | [ai-engineering-workflow.md](ai-engineering-workflow.md) |
| Choose which model tier to use for a task | [model-routing.md](model-routing.md) |
| Track compliance/session traceability requirements | [audit-traceability.md](audit-traceability.md) |
| Measure Claude Code adoption on this project | [adoption-metrics.md](adoption-metrics.md) |
| Set up an MCP server integration | [mcp-integrations.md](mcp-integrations.md) |
| Read a guided tour of the actual codebase | [code-walkthrough.md](code-walkthrough.md) |
| A full business + technical overview, with role-based quick starts | [framework-overview-onboarding.md](framework-overview-onboarding.md) — the deeper companion to [docs/onboarding.md](../onboarding.md), which stays the entry point |
| Write, restructure, or review any documentation in this repository | [documentation-style-guide.md](documentation-style-guide.md) |

## Claude Code tooling guides — by intent

These are about using Claude Code itself, not about the RAG framework it's operating on.

| You want to... | Go to |
|---|---|
| A project-specific "what's actually configured here" overview | [claude-code.md](claude-code.md) |
| The full development workflow, with worked examples | [claude-code-complete-development-guide.md](claude-code-complete-development-guide.md) |
| A governance-level hub (security layers, KPIs, subagents, links to the rest) | [CLAUDE-CODE-COMPLETE-GUIDE.md](CLAUDE-CODE-COMPLETE-GUIDE.md) |
| First-time setup and your first task | [onboarding-claude-code.md](onboarding-claude-code.md) |
| Get up to speed running Claude Code sub-agents in parallel | [subagents-parallelization.md](subagents-parallelization.md) |
| Understand parallelization patterns (tool/component/agentic level) | [claude-code-parallelization-orchestration.md](claude-code-parallelization-orchestration.md) |
| Look up every `settings.json` key | [claude-code-settings-reference.md](claude-code-settings-reference.md) |
| Configure subagents, skills, path-scoped rules, hooks | [claude-code-advanced-config.md](claude-code-advanced-config.md) |
| Set up an MCP server for Claude Code itself | [claude-code-mcp-setup.md](claude-code-mcp-setup.md) |
| Set up a plugin marketplace | [claude-code-plugins-marketplaces.md](claude-code-plugins-marketplaces.md) |
| Deploy Claude Code across an organization (MDM, managed settings) | [claude-code-enterprise-deployment.md](claude-code-enterprise-deployment.md) |

---

Two former entries here — a native multi-agent design guide and a commercial staffing plan —
moved to [docs/archive/](../archive/) on 2026-08-06 (superseded content, low ongoing utility;
see `docs/archive/README.md`).

For the framework's own architecture, ADRs, and API reference, see
[docs/_index.md](../_index.md) — this file only indexes `docs/guides/`.
