# Claude Code Plugins & Marketplaces

Complete guide to Claude Code plugin system, marketplace discovery, and team distribution.

> **Scope.** This is general Claude Code reference material. **This project defines no plugin and
> no marketplace**; nothing here is active in this repository today.

**Table of Contents**
1. [Plugin System Overview](#plugin-system-overview) — What plugins are
2. [Discovering Plugins](#discovering-plugins) — Finding & installing
3. [Plugin Configuration](#plugin-configuration) — Management by scope
4. [Marketplace Setup](#marketplace-setup) — Creating team marketplaces
5. [Enterprise Governance](#enterprise-governance) — Managed restrictions
6. [Plugin Development](#plugin-development) — Building custom plugins
7. [Examples](#examples) — Real-world setups

---

## Plugin System Overview

### What are Plugins?

**Plugins** extend Claude Code with bundled capabilities:
- **Skills** — Reusable task workflows
- **Agents** — Specialized AI assistants
- **Hooks** — Automation at lifecycle events
- **MCP Servers** — External integrations
- **Commands** — Custom slash commands

### Plugin vs. Skill

| Feature | Plugin | Skill |
|---------|--------|-------|
| Discovery | From marketplace | `~/.claude/skills/` or `.claude/skills/` |
| Installation | Via `/plugin` command | Manual creation |
| Sharing | Via marketplace | Copy file + import in CLAUDE.md |
| Bundling | Skills + Agents + Hooks | Single workflow |
| Team distribution | Easy (marketplace) | Manual (file sharing) |

### Where Plugins Come From

1. **Official Marketplace** — Anthropic-maintained plugins
2. **Team Marketplace** — Your organization's plugins
3. **Community Marketplace** — Open source plugins
4. **Custom Marketplace** — Self-hosted plugins

---

## Discovering Plugins

### Using `/plugin` Command

```
/plugin list                    # Show all available plugins
/plugin search formatter        # Find plugins matching "formatter"
/plugin marketplace list        # Show all registered marketplaces
/plugin marketplace add         # Add a new marketplace source
/plugin install formatter@official  # Install plugin from marketplace
/plugin enable formatter@official    # Turn on plugin
/plugin disable formatter@official   # Turn off plugin
/plugin details formatter@official   # Show plugin details
```

### First-Time Marketplace Setup

When opening a project with `extraKnownMarketplaces` configured:

1. Claude Code detects new marketplace
2. Prompt appears: "Trust marketplace 'team-tools'?"
3. After trust: "Install recommended plugins?"
4. Plugins install to `.claude/settings.json`

**Result**: Team tools available to everyone on the project

---

## Plugin Configuration

### Plugin Settings

| Setting | Type | Scope | Purpose |
|---------|------|-------|---------|
| `enabledPlugins` | object | User/Project/Local | Enable/disable per plugin |
| `extraKnownMarketplaces` | object | Project | Discover additional marketplaces |
| `strictKnownMarketplaces` | array | Managed only | Allowlist approved marketplaces |
| `strictPluginOnlyCustomization` | bool/array | Managed only | Block non-plugin customization |
| `pluginTrustMessage` | string | Managed only | Custom message in trust dialog |

### Enabling/Disabling Plugins

**Format**: `"plugin-name@marketplace": true/false`

```json
{
  "enabledPlugins": {
    "formatter@official": true,
    "deployer@team-tools": true,
    "experimental@personal": false
  }
}
```

**Where to configure:**
- **User scope** (`~/.claude/settings.json`): Personal preferences
- **Project scope** (`.claude/settings.json`): Team preferences (in git)
- **Local scope** (`.claude/settings.local.json`): Machine overrides (gitignored)

**Precedence:**
```
User:     { "formatter@official": false }
Project:  { "formatter@official": true }
Result:   true (Project wins)

To disable a project-enabled plugin on your machine:
Set in .claude/settings.local.json: { "formatter@official": false }
```

---

## Marketplace Setup

### Official Marketplace

Anthropic-maintained marketplace of vetted plugins.

**Default behavior:**
- Available automatically
- No explicit configuration needed
- Plugins auto-update by default

### Extra Known Marketplaces

Register additional marketplaces for team plugins.

**Configuration**:
```json
{
  "extraKnownMarketplaces": {
    "team-tools": {
      "source": {
        "source": "github",
        "repo": "acme-corp/claude-plugins"
      },
      "autoUpdate": true
    },
    "security-tools": {
      "source": {
        "source": "github",
        "repo": "acme-corp/security-plugins",
        "ref": "v1.0"
      }
    }
  }
}
```

**Where to configure:**
- Best in `.claude/settings.json` (project scope)
- So entire team discovers it

**User experience:**
1. Open project
2. "Trust marketplace 'team-tools'?"
3. "Install recommended plugins?"
4. Plugins available

### Marketplace Source Types

#### GitHub Repository

```json
{
  "source": "github",
  "repo": "acme-corp/claude-plugins",
  "ref": "v2.0",           // optional: branch/tag/SHA
  "path": "marketplace"    // optional: subdirectory
}
```

#### Git Repository (Any Provider)

```json
{
  "source": "git",
  "url": "https://gitlab.example.com/tools/plugins.git",
  "ref": "production",
  "path": "approved"
}
```

#### NPM Package

```json
{
  "source": "npm",
  "package": "@acme-corp/claude-plugins"
}
```

#### URL-Based

```json
{
  "source": "url",
  "url": "https://plugins.example.com/marketplace.json",
  "headers": {
    "Authorization": "Bearer ${PLUGINS_TOKEN}"
  }
}
```

#### File System

```json
{
  "source": "file",
  "path": "/opt/acme/plugins/marketplace.json"
}
```

#### Directory

```json
{
  "source": "directory",
  "path": "/usr/local/share/claude/plugins"
}
```

### Creating a Team Marketplace

**Step 1: Create GitHub Repository**
```bash
git init acme-corp/claude-plugins
mkdir -p plugins/code-formatter
mkdir -p plugins/test-runner
```

**Step 2: Create marketplace.json**
```json
{
  "name": "ACME Team Tools",
  "version": "1.0.0",
  "description": "Curated plugins for ACME engineers",
  "plugins": [
    {
      "name": "code-formatter",
      "description": "Format code with team standards",
      "version": "1.0.0",
      "source": {
        "source": "github",
        "repo": "acme-corp/code-formatter"
      }
    },
    {
      "name": "test-runner",
      "description": "Run tests and report results",
      "version": "1.0.0",
      "source": {
        "source": "github",
        "repo": "acme-corp/test-runner"
      }
    }
  ]
}
```

**Step 3: Register in Projects**
```json
{
  "extraKnownMarketplaces": {
    "team-tools": {
      "source": {
        "source": "github",
        "repo": "acme-corp/claude-plugins"
      }
    }
  }
}
```

---

## Enterprise Governance

### Managed Marketplace Restrictions

**Use case**: IT needs to enforce which plugins teams can use.

**Configuration in managed-settings.json**:

```json
{
  "strictKnownMarketplaces": [
    {
      "source": "github",
      "repo": "acme-corp/approved-plugins"
    },
    {
      "source": "github",
      "repo": "acme-corp/security-tools",
      "ref": "v2.0"
    }
  ]
}
```

**Effect:**
- ✅ Only these marketplaces allowed
- ❌ Users cannot add other marketplaces
- ❌ Plugins from unapproved sources blocked

### Managed Plugin Force-Enabling

Force entire team to use specific plugins:

```json
{
  "enabledPlugins": {
    "security-scanner@official": true,
    "audit-logger@internal": true
  }
}
```

**Effect:**
- Users cannot disable these plugins
- Plugins run on every session

### Blocking Non-Plugin Customization

Restrict skills, agents, hooks to only come from plugins:

```json
{
  "strictPluginOnlyCustomization": ["skills", "hooks"]
}
```

**Effect:**
- ❌ No user-created skills (`~/.claude/skills/`)
- ❌ No project skills (`.claude/skills/`)
- ❌ No user hooks in settings.json
- ✅ Only plugin skills/hooks allowed

**Granular control**:
```json
{
  "strictPluginOnlyCustomization": ["skills", "hooks"]
  // Only lock skills and hooks, allow custom agents
}
```

---

## Plugin Development

### Plugin Structure

```
my-plugin/
├── PLUGIN.md               # Plugin metadata & interface
├── skills/                 # Skill files
│   └── my-skill.md
├── agents/                 # Agent files
│   └── my-agent.md
├── hooks/                  # Hook configurations
│   └── hooks.json
└── MANIFEST.json          # Plugin package info
```

### Plugin Manifest (PLUGIN.md)

```markdown
---
name: "Code Formatter"
description: "Format code with team standards"
version: "1.0.0"
author: "ACME Team"
defaultEnabled: false
---

# Code Formatter Plugin

Automatically formats code using project standards.

## Features

- Python: Black + isort
- TypeScript: Prettier
- Markdown: Prettier

## Configuration

Set preferred formatter in `.claude/settings.json`:

\`\`\`json
{
  "enabledPlugins": {
    "code-formatter@team-tools": true
  }
}
\`\`\`

## Skills Provided

- `/format-file` — Format current file
- `/format-project` — Format entire project
```

### Creating a Skill Plugin

**skills/format-code.md**:
```markdown
---
name: format-code
when_to_use: Format code with team standards (Black, Prettier)
---

# Format Code

Formats code in the current project using:
- Python: Black + isort
- TypeScript: Prettier
- Markdown: Prettier

## How to Use

\`/format-code python\` — Format all Python files
\`/format-code typescript\` — Format all TypeScript files
\`/format-code all\` — Format everything

## Implementation

Uses configured formatters to reformat code automatically.
```

### Creating an Agent Plugin

> **Correction (2026-06-22, revised)**:
> - There's no `instructions:` frontmatter field — put the instructions in the markdown body, as
>   below (see claude-code-advanced-config.md "Creating a Subagent" for the full real field
>   list — `name`/`description` are required; `tools`, `model`, `permissionMode`, `memory`, and
>   others are real optional fields).
> - `claude-opus-4-6` is a real model ID (just not the current latest, `claude-opus-4-8` — an
>   earlier revision of this note wrongly called it fake).
> - There's also no `/agent <name> <args>` slash command, but `claude --agent <name>` and the
>   `agent` settings.json key (to set a default) **are** real — see the correction in
>   claude-code-advanced-config.md "Using a Subagent".

**agents/code-reviewer.md**:
```markdown
---
name: code-reviewer
description: Code reviewer specializing in security and performance
model: opus
---

# Code Reviewer Agent

Specialized agent for thorough code reviews. Always check for:
- Security vulnerabilities
- Performance issues
- Code style violations
- Missing tests
- Documentation gaps

## Tools Available

- Read code files
- Search codebase
- Run linters
- View test coverage

## Example Usage

Mention it in chat: `@code-reviewer review this PR`
```

### Creating Hook Plugin

> **Correction**: no `filePattern` field, no `{file}` template — `matcher` matches tool name only; the command must read the file path itself from the JSON piped to stdin (see claude-code-advanced-config.md "Hooks Advanced" for the `jq` pattern).

**hooks.json**:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "file=$(jq -r .tool_input.file_path); [[ \"$file\" == *.py ]] && black \"$file\""
          }
        ]
      }
    ]
  }
}
```

---

## Examples

### Example 1: Simple Team Marketplace

```json
{
  "extraKnownMarketplaces": {
    "acme-tools": {
      "source": {
        "source": "github",
        "repo": "acme-corp/claude-plugins"
      },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "code-formatter@acme-tools": true,
    "test-runner@acme-tools": true
  }
}
```

### Example 2: Enterprise Governance

```json
{
  "strictKnownMarketplaces": [
    {
      "source": "github",
      "repo": "acme-corp/approved-plugins"
    },
    {
      "source": "github",
      "repo": "acme-corp/security-tools",
      "ref": "v2.0"
    }
  ],
  "strictPluginOnlyCustomization": ["skills", "hooks"],
  "allowedChannelPlugins": [
    {
      "marketplace": "official",
      "plugin": "slack"
    }
  ],
  "enabledPlugins": {
    "audit-logger@official": true,
    "security-scanner@internal": true
  }
}
```

### Example 3: Development Team Setup

**.claude/settings.json**:
```json
{
  "extraKnownMarketplaces": {
    "dev-tools": {
      "source": {
        "source": "github",
        "repo": "publicis-corp/dev-plugins"
      },
      "autoUpdate": true
    },
    "internal-docs": {
      "source": {
        "source": "url",
        "url": "https://plugins.internal.example.com/marketplace.json"
      }
    }
  },
  "enabledPlugins": {
    "git-helper@dev-tools": true,
    "test-runner@dev-tools": true,
    "docs-search@internal-docs": true
  }
}
```

---

## Troubleshooting

### Plugin Not Found

**Problem**: `/plugin list` shows no plugins

**Solutions**:
1. Check marketplace is registered: `/plugin marketplace list`
2. Verify marketplace source: `git clone <repo>` works
3. Ensure marketplace.json is valid JSON

### Plugin Failed to Install

**Problem**: Installation fails midway

**Solutions**:
1. Check GitHub token: `echo $GITHUB_TOKEN`
2. Verify repo permissions (not private without auth)
3. Check network: `curl https://api.github.com`

### Plugin Not Loading

**Problem**: Plugin installed but not showing skills

**Solutions**:
1. Check enabled: `enabledPlugins` should have `true`
2. Verify plugin name matches exactly: `name@marketplace`
3. Restart Claude Code: `claude` will reload

---

## See Also

- [Claude Code Settings Reference](./claude-code-settings-reference.md)
- [Claude Code MCP Setup](./claude-code-mcp-setup.md)
- [Claude Code Advanced Configuration](./claude-code-advanced-config.md)
- [Claude Code Enterprise Deployment](./claude-code-enterprise-deployment.md)
