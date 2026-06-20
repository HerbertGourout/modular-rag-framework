# Claude Code Advanced Configuration

Advanced topics: subagents, skills, path-scoped rules, hooks, sandbox, and authentication.

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

**File**: `.claude/agents/code-reviewer.md`

```markdown
---
name: code-reviewer
model: claude-opus-4-6
description: Specialized code review agent
permissions:
  allow:
    - "Read(src/**)"
    - "Read(tests/**)"
    - "Bash(npm run lint)"
  deny:
    - "Edit(**)"
    - "Bash(npm publish)"
autoMemory: true
---

# Code Reviewer Agent

Expert code reviewer focused on quality and security.

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

```bash
# Run main thread as code-reviewer agent
claude --agent code-reviewer

# Set default agent for all sessions
echo '{"agent": "code-reviewer"}' >> ~/.claude/settings.json

# Switch agent mid-session
/agent code-reviewer
```

### Subagent Memory

Each subagent maintains its own auto memory:

```
~/.claude/projects/<project>/memory/
├── MEMORY.md                  # Main session memory
├── agents/
│   ├── code-reviewer/
│   │   └── MEMORY.md          # Code reviewer learnings
│   ├── docs-writer/
│   │   └── MEMORY.md          # Docs writer learnings
```

Enable per subagent:

```markdown
---
name: code-reviewer
autoMemory: true
---
```

---

## Skills Management

### What are Skills?

**Skills** are reusable workflows:
- Stored as `.md` files
- Loaded on demand or automatically
- Can invoke with `/skill-name`
- Saved to `~/.claude/skills/` or `.claude/skills/`

### Skill File Format

**File**: `.claude/skills/deploy-to-staging.md`

```markdown
---
name: deploy-to-staging
when_to_use: Deploy code changes to staging environment
example_invocation: /deploy-to-staging
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
├── build-and-test.md
├── deploy-to-staging.md
├── deploy-to-production.md
├── security/
│   ├── security-scan.md
│   └── dependency-audit.md
└── documentation/
    ├── generate-api-docs.md
    └── update-changelog.md
```

### Controlling Skill Visibility

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

| Hook | Event | Usage |
|------|-------|-------|
| `PreToolUse` | Before tool execution | Validate/block operations |
| `PostToolUse` | After tool execution | Auto-formatting, linting |
| `ConfigChange` | Settings changed | Notify/reload config |
| `InstructionsLoaded` | Session starts | Log what rules loaded |
| `ContextWindows` | Context window changes | Track memory usage |

### Post-Tool-Use Hook (Most Common)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Create",
        "filePattern": "src/**/*.py",
        "hooks": [
          {
            "type": "command",
            "command": "ruff check {file} --select E,F,I --fix"
          }
        ]
      },
      {
        "matcher": "Edit",
        "filePattern": "src/**/*.ts",
        "hooks": [
          {
            "type": "command",
            "command": "eslint {file} --fix"
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

```
claude-opus-4-6        # Most capable, most expensive
claude-sonnet-4-6      # Balanced (default)
claude-haiku-4-5       # Fast, cheap
```

### Fallback Chains

When primary model overloaded, fall back to others:

```json
{
  "model": "claude-opus-4-6",
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
    "claude-opus-4-6": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/anthropic.claude-opus-4-6-20250514-v1:0",
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
  "model": "claude-opus-4-6",
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
