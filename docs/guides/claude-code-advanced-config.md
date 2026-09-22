# Claude Code Advanced Configuration

Advanced topics: subagents, skills, path-scoped rules, hooks, sandbox, and authentication.

> **Scope.** This is general Claude Code reference material. For what this repository actually
> configures — its eight subagents, its skills, its single post-edit hook and its permission
> boundaries — see [claude-code.md](claude-code.md).

**Table of Contents**
1. [Subagents](#subagents) — Specialized AI assistants
2. [Skills Management](#skills-management) — Reusable workflows
3. [Path-Scoped Rules](#path-scoped-rules) — Context efficiency
4. [Hooks Advanced](#hooks-advanced) — Automation deep dive
5. [Extended Thinking](#extended-thinking) — GPT-4 level reasoning
6. [Model Selection](#model-selection) — Fallback chains
7. [Examples](#examples) — Real-world setups

---

## Subagents

### What are Subagents?

**Subagents** are specialized AI assistants with their own:
- System prompt (instructions)
- Tool restrictions (permissions)
- Model selection (which LLM)
- Memory (auto memory)

Use subagents for:
- Code review specialist
- Security auditor
- Documentation writer
- DevOps engineer
- Performance analyst

### Storage Locations

| Location | Scope | Files | Usage |
|----------|-------|-------|-------|
| `~/.claude/agents/` | User | Available all projects | Personal preferences |
| `.claude/agents/` | Project | Checked in git | Team workflows |
| Not from plugins | — | — | Blocked if `strictPluginOnlyCustomization: ["agents"]` |

### Creating a Subagent

**Illustrative file**: `.claude/agents/code-reviewer.md` (not currently present in this project;
the checked-in reviewer is `.claude/agents/architecture-reviewer.md`)

> **Correction (2026-06-22, revised)**: an earlier pass through this doc over-corrected.
>
> - Only `name` and `description` are required, but there are **15 real optional fields**, not
>   "exactly four": `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`,
>   `mcpServers`, `hooks`, `memory`, `background`, `effort`, `isolation`, `color`,
>   `initialPrompt`.
> - What's genuinely **not** real: a `permissions` block with `allow`/`deny` path arrays (the
>   real, much simpler equivalent is the `permissionMode` enum: `default`/`acceptEdits`/`auto`/
>   `dontAsk`/`bypassPermissions`/`plan`), an `autoMemory` boolean (the real field is `memory:
>   user|project|local`, see below), and `expertise_level`/`domain`/`instructions` (not
>   recognized — put that content in the body).
> - Also: `claude-opus-4-6` **is** a real model ID (just not the current latest, which is
>   `claude-opus-4-8`) — an earlier note here wrongly called it fake.

```markdown
---
name: code-reviewer
description: Specialized code review agent
model: opus
tools: Read, Grep, Bash
permissionMode: dontAsk
memory: project
---

# Code Reviewer Agent

Expert code reviewer focused on quality and security. Only reads src/** and tests/**; never edits files; runs `npm run lint` to verify findings.

## Responsibilities

- Security vulnerability detection
- Performance optimization suggestions
- Code style compliance
- Test coverage analysis
- Documentation completeness

## Review Checklist

- [ ] No hardcoded secrets
- [ ] No SQL injection risks
- [ ] Adequate test coverage (>80%)
- [ ] Type safety (where applicable)
- [ ] Documentation complete
```

### Using a Subagent

> **Correction (2026-06-22, revised)**: `claude --agent <name>` and the top-level `agent` settings.json key **are real** — an earlier note here wrongly called them fake. What's genuinely not real is a `/agent <name>` slash command with trailing arguments; the real chat-time invocation is `@`-mention.

```bash
# Run main thread as the code-reviewer agent for this session
claude --agent code-reviewer

# Set it as the default agent for all sessions (real settings.json key)
# .claude/settings.json: { "agent": "code-reviewer" }
```

```
# Mid-conversation: Claude delegates automatically when a task matches the
# subagent's `description`, or you @-mention it explicitly:
@code-reviewer please review this diff for security issues
# (manual form without the picker: @agent-code-reviewer)
```

### Subagent Memory

> **Correction (2026-06-22, revised)**: per-subagent memory **is real** — an earlier note here wrongly denied it. The real field is `memory: user|project|local` (not `autoMemory: true`), and the real path depends on scope:

| Scope | Location |
|-------|----------|
| `user` | `~/.claude/agent-memory/<name-of-agent>/` |
| `project` | `.claude/agent-memory/<name-of-agent>/` (shareable via version control — recommended default) |
| `local` | `.claude/agent-memory-local/<name-of-agent>/` (project-specific, not checked in) |

When enabled, Read/Write/Edit are auto-granted for that directory, and the first 200 lines (or 25KB) of its `MEMORY.md` are injected into the subagent's system prompt automatically.

---

## Skills Management

### What are Skills?

**Skills** are reusable workflows:
- Stored as a **directory** containing `SKILL.md` (not a flat `.md` file — see correction below)
- Invoked explicitly (by Claude or a user typing `/skill-name`) — never auto-loaded just because a path matched (that's what path-scoped Rules are for, see next section)
- Saved to `~/.claude/skills/<name>/` (user, all projects) or `.claude/skills/<name>/` (project, checked in)

### Skill File Format

> **Correction (2026-06-22)**: the path must be `.claude/skills/deploy-to-staging/SKILL.md` (a directory per skill), not a flat `.claude/skills/deploy-to-staging.md` file — flat files are silently never discovered. Frontmatter supports only `name` and `description`; `when_to_use`/`example_invocation` are not real fields (put that guidance in the body instead).

**File**: `.claude/skills/deploy-to-staging/SKILL.md`

```markdown
---
name: deploy-to-staging
description: Deploy code changes to staging environment
---

# Deploy to Staging

Automated deployment workflow for staging environment.

## Steps

1. Validate all tests pass
2. Build Docker image
3. Push to staging registry
4. Update Kubernetes manifests
5. Deploy to staging cluster
6. Run smoke tests
7. Report deployment status

## How to Use

Invoke with `/deploy-to-staging`

Claude will:
- Check all tests pass: \`npm test\`
- Build: \`docker build -t staging:latest .\`
- Deploy: \`kubectl apply -f k8s/staging/\`
- Verify: \`npm run smoke-tests\`

## Success Criteria

✅ All tests pass
✅ Docker image builds
✅ Deployment succeeds
✅ Smoke tests pass
✅ Slack notification sent
```

### Organizing Skills

```
.claude/skills/
├── build-and-test/SKILL.md
├── deploy-to-staging/SKILL.md
├── deploy-to-production/SKILL.md
├── security-scan/SKILL.md
└── dependency-audit/SKILL.md
```

(Each skill is its own directory; there's no nested-folder grouping like `security/`/`documentation/` shown in earlier drafts of this doc — `.claude/skills/` is a flat list of skill directories.)

### Controlling Skill Visibility

> **Not independently verified (2026-06-22)**: `skillOverrides`, `skillListingBudgetFraction`, `maxSkillDescriptionChars`, and `strictPluginOnlyCustomization` (mentioned earlier in this file) were not confirmed against official docs during this audit — treat them as unverified rather than assume they work. Everything else on this page up to this point (subagent frontmatter, skill directory format, hook events/matcher, model IDs) was checked and corrected.

**Hide or collapse skills** with `skillOverrides`:

```json
{
  "skillOverrides": {
    "legacy-task": "off",           // Don't show
    "internal-tool": "name-only",   // Show name, no description
    "beta-feature": "user-invocable-only"  // Can call, won't suggest
  }
}
```

### Skill Listing Budget

Control how much context skills consume:

```json
{
  "skillListingBudgetFraction": 0.02,  // 2% of context window
  "maxSkillDescriptionChars": 2048      // Max chars per skill
}
```

---

## Path-Scoped Rules

### What are Path-Scoped Rules?

**Rules** are instructions that load ONLY when Claude reads matching files.

Benefits:
- ✅ Reduce context bloat
- ✅ Only relevant rules in context
- ✅ Better adherence (less noise)
- ✅ Scale to large projects

### Creating Path-Scoped Rules

**File**: `.claude/rules/frontend-react.md`

```markdown
---
paths:
  - "src/components/**/*.tsx"
  - "src/hooks/**/*.ts"
---

# Frontend Development Rules

## React Component Guidelines

- Functional components (no class components)
- Use React hooks for state
- Memoize with React.memo if needed
- PropTypes required for all props

## File Organization

```
src/
├── components/
│   ├── Button.tsx
│   ├── Button.stories.tsx
│   └── Button.test.tsx
├── hooks/
│   └── useLocalStorage.ts
```

## Testing Requirements

Every component must have:
- Unit tests in .test.tsx
- Storybook stories in .stories.tsx
- >80% coverage

## Styling

- Use TailwindCSS classes
- No inline styles
- Responsive breakpoints required
```

### Multiple Path Patterns

```markdown
---
paths:
  - "src/**/*.{ts,tsx}"           # TypeScript files
  - "tests/**/*.test.ts"          # Test files
  - "lib/**/*.ts"                 # Library files
---
```

### User-Level Rules

Create personal rules applied across ALL projects:

```
~/.claude/rules/
├── my-preferences.md
├── testing-standards.md
└── documentation.md
```

### Sharing Rules with Symlinks

Link shared rules into multiple projects:

```bash
ln -s ~/shared-rules/security.md .claude/rules/security.md
ln -s ~/shared-rules/api-design.md .claude/rules/api-design.md
```

---

## Hooks Advanced

### Hook Types

> **Correction (2026-06-22)**: `ConfigChange`, `InstructionsLoaded`, and `ContextWindows` are not real hook events — they were invented. The real lifecycle events are:

| Hook | Event | Usage |
|------|-------|-------|
| `PreToolUse` | Before tool execution | Validate/block operations |
| `PostToolUse` | After tool execution | Auto-formatting, linting |
| `Notification` | Claude sends a notification | Custom alerting |
| `UserPromptSubmit` | User submits a prompt | Inject extra context, validate input |
| `Stop` | Main agent finishes responding | Cleanup, summaries |
| `SubagentStop` | A subagent finishes | Aggregate subagent results |
| `PreCompact` | Before context compaction | Save state before it's summarized |
| `SessionStart` / `SessionEnd` | Session begins/ends | Setup/teardown |

### Post-Tool-Use Hook (Most Common)

> **Correction**: there is no `filePattern` field, and no `{file}` template substitution in the `command` string — `matcher` only matches the **tool name**. Claude Code pipes a JSON payload (including `tool_input.file_path`) to the hook command's **stdin**; the command itself must parse that (e.g. with `jq`) if it needs to act conditionally on the file path:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Create",
        "hooks": [
          {
            "type": "command",
            "command": "file=$(jq -r .tool_input.file_path); case \"$file\" in *.py) ruff check \"$file\" --select E,F,I --fix;; *.ts) eslint \"$file\" --fix;; esac"
          }
        ]
      }
    ]
  }
}
```

### Pre-Tool-Use Hook (Validation)

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "specifier": "rm -rf",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Dangerous command detected'; exit 1"
          }
        ]
      }
    ]
  }
}
```

### HTTP Hooks

Trigger webhooks when tool executes:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "specifier": "npm run deploy",
        "hooks": [
          {
            "type": "http",
            "url": "https://hooks.example.com/deploy",
            "method": "POST",
            "headers": {
              "Authorization": "Bearer ${HOOK_TOKEN}"
            },
            "body": {
              "event": "deployment",
              "status": "started"
            }
          }
        ]
      }
    ]
  }
}
```

**Restrict HTTP URLs**:
```json
{
  "allowedHttpHookUrls": [
    "https://hooks.example.com/*",
    "http://localhost:*"
  ],
  "httpHookAllowedEnvVars": ["HOOK_TOKEN", "SLACK_TOKEN"]
}
```

---

## Extended Thinking

### What is Extended Thinking?

Extended thinking enables Claude to reason deeply before responding:
- Solves complex problems
- Better code analysis
- Deeper understanding
- Slower (takes more tokens)

### Enable Extended Thinking

```json
{
  "alwaysThinkingEnabled": true,
  "showThinkingSummaries": true
}
```

### Per-Session

```bash
claude /effort xhigh   # Enable extended thinking
/clear                 # Disable for this session
```

### Via Environment

```bash
export ANTHROPIC_THINKING_BUDGET_TOKENS=10000
claude
```

---

## Model Selection

### Available Models

Model IDs are updated frequently — the ones below (as of this documentation pass) are the
current Claude 5 family; treat any specific ID in this guide's JSON examples further down as
illustrative syntax, not a claim about which model is current at the time you're reading this:

```
claude-opus-5           # Most capable, most expensive
claude-sonnet-5         # Balanced (default)
claude-haiku-4-5-20251001  # Fast, cheap
```

### Fallback Chains

When primary model overloaded, fall back to others:

```json
{
  "model": "claude-opus-4-8",
  "fallbackModel": ["claude-sonnet-4-6", "claude-haiku-4-5"]
}
```

### Restrict Available Models

```json
{
  "availableModels": ["sonnet", "haiku"],
  "enforceAvailableModels": true
}
```

Result: Users can only select Sonnet or Haiku.

### Model Overrides

Map Anthropic models to provider-specific IDs (Bedrock, Vertex):

```json
{
  "modelOverrides": {
    "claude-opus-4-8": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/anthropic.claude-opus-4-8-20250514-v1:0",
    "claude-sonnet-4-6": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/anthropic.claude-sonnet-4-6-20250514-v1:0"
  }
}
```

---

## Examples

### Example 1: Security-Focused Setup

```json
{
  "permissions": {
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(sudo *)",
      "Bash(curl -X POST *)"
    ]
  },
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws"]
    }
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "specifier": "rm -rf",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Dangerous command blocked'; exit 1"
          }
        ]
      }
    ]
  }
}
```

### Example 2: High-Performance Setup

```json
{
  "model": "claude-opus-4-8",
  "fallbackModel": ["claude-sonnet-4-6"],
  "alwaysThinkingEnabled": true,
  "effortLevel": "xhigh",
  "skillListingBudgetFraction": 0.03,
  "autoMemoryEnabled": true
}
```

### Example 3: Large Codebase Setup

```json
{
  "skillListingBudgetFraction": 0.02,
  "autoCompactEnabled": true,
  "claudeMdExcludes": [
    "**/vendor/**",
    "**/node_modules/**"
  ]
}
```

---

## See Also

- [Claude Code Settings Reference](./claude-code-settings-reference.md)
- [Claude Code MCP Setup](./claude-code-mcp-setup.md)
- [Claude Code Plugins & Marketplaces](./claude-code-plugins-marketplaces.md)
- [Claude Code Enterprise Deployment](./claude-code-enterprise-deployment.md)
