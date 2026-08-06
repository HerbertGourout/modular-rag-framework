# Claude Code Settings Reference

Complete guide to Claude Code configuration system with all 100+ settings, scopes, and precedence rules.

**Table of Contents**
1. [Configuration Scopes](#configuration-scopes) — 5-level hierarchy
2. [Settings by Category](#settings-by-category) — Grouped reference
3. [Permission Rules Syntax](#permission-rules-syntax) — Advanced patterns
4. [Sandbox Configuration](#sandbox-configuration) — Security isolation
5. [Precedence & Merge Behavior](#precedence--merge-behavior) — How settings interact
6. [Examples](#examples) — Real-world configurations

---

## Configuration Scopes

Claude Code uses a **5-level scope system** where higher levels override lower ones.

### Scope Hierarchy (Highest to Lowest Priority)

| Scope | File/Location | Who | Shared | Can Be Overridden |
|-------|---------------|-----|--------|------------------|
| **1. Managed** | System-wide deployment | IT/DevOps | Organization | ❌ NEVER |
| **2. CLI** | `--settings <json>` | Individual | One session | ✅ Only by Managed |
| **3. Local** | `.claude/settings.local.json` | You | Per machine | ✅ By CLI/Managed |
| **4. Project** | `.claude/settings.json` | Team | Version control | ✅ By Local/CLI/Managed |
| **5. User** | `~/.claude/settings.json` | You | All projects | ✅ By all above |

### When to Use Each Scope

**User Scope** (`~/.claude/settings.json`):
- Personal preferences across ALL projects
- Your favorite theme, editor mode, voice settings
- API credentials (stored securely)
- Personal tooling preferences
- Example: `"theme": "dark"`, `"editorMode": "vim"`

**Project Scope** (`.claude/settings.json`):
- Team-shared standards for THIS repository
- Committed to git, visible to all team members
- Project-specific permissions, MCP servers, plugins
- Build environment setup
- Example: `"permissions": {"deny": ["Read(./.env)"]}`

**Local Scope** (`.claude/settings.local.json`):
- Personal overrides for THIS project ONLY
- **NOT** committed to git (auto-gitignored)
- Machine-specific settings
- Example: `"env": {"MRAG_OPENAI_API_KEY": "sk-..."}`

**CLI Scope** (`--settings <file-or-json>`):
- One-time override for a specific session
- Highest precedence except Managed
- Example: `claude --settings '{"verbose": true}'`

**Managed Scope** (`managed-settings.json`, MDM, Group Policy):
- Organization-wide enforcement
- Deployed by IT/DevOps
- CANNOT be overridden by anything
- Example: Block all LLM adapters (V2+ reserved)

---

## Settings by Category

### Model Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | "claude-sonnet-4-6" | Default model for main session |
| `fallbackModel` | string[] | — | Chain of fallback models if primary fails (max 3) |
| `availableModels` | string[] | — | Restrict which models users can select |
| `enforceAvailableModels` | boolean | false | Also constrain default model to allowlist |
| `advisorModel` | string | "opus" | Model for server-side advisor tool |

**Example: Fallback Chain**
```json
{
  "model": "opus",
  "fallbackModel": ["claude-sonnet-4-6", "claude-haiku-4-5"]
}
```
When Opus is overloaded → switch to Sonnet, then Haiku. (Use the alias `"opus"`/`"sonnet"`/`"haiku"` to always track the latest model in that tier, or a full dated ID like `claude-opus-4-8` to pin a specific snapshot. **Self-correction (2026-06-22)**: an earlier revision of this note claimed `claude-opus-4-6` "does not exist" — that was wrong. It's a real, valid Opus snapshot, just not the current latest one (`claude-opus-4-8`, as of this session). Pinning an older snapshot is legitimate if you want reproducible behavior; use the `opus` alias instead if you want to always track the newest release.)

### Permissions & Security

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `permissions.allow` | string[] | [] | Tools/actions to auto-approve |
| `permissions.ask` | string[] | [] | Tools/actions to prompt before use |
| `permissions.deny` | string[] | [] | Tools/actions to block |
| `permissions.defaultMode` | enum | "default" | Permission mode: default/acceptEdits/plan/auto/dontAsk/bypassPermissions |
| `permissions.additionalDirectories` | string[] | [] | Extra directories for file access |
| `permissions.skipDangerousModePermissionPrompt` | boolean | false | Skip confirmation before entering bypassPermissions |
| `disableBypassPermissionsMode` | string | — | Set to "disable" to prevent --dangerously-skip-permissions |

**Example: Secure Setup**
```json
{
  "permissions": {
    "allow": [
      "Bash(npm run *)",
      "Read(./docs/**)",
      "Edit(src/**)"
    ],
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(curl *)"
    ],
    "defaultMode": "acceptEdits"
  }
}
```

### Sandbox & Isolation

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `sandbox.enabled` | boolean | false | Enable bash sandboxing (macOS/Linux/WSL2) |
| `sandbox.failIfUnavailable` | boolean | false | Exit if sandbox unavailable |
| `sandbox.autoAllowBashIfSandboxed` | boolean | true | Auto-approve bash when sandboxed |
| `sandbox.excludedCommands` | string[] | [] | Commands to run outside sandbox |
| `sandbox.filesystem.allowWrite` | string[] | [] | Paths where commands can write |
| `sandbox.filesystem.denyWrite` | string[] | [] | Paths where commands cannot write |
| `sandbox.filesystem.denyRead` | string[] | [] | Paths where commands cannot read |
| `sandbox.network.allowedDomains` | string[] | [] | Domains allowed for outbound traffic |
| `sandbox.network.deniedDomains` | string[] | [] | Domains blocked for outbound traffic |
| `sandbox.network.allowUnixSockets` | string[] | [] | Unix socket paths accessible in sandbox |

**Example: Secure Development**
```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "filesystem": {
      "allowWrite": ["/tmp/build", "~/.kube"],
      "denyRead": ["~/.aws/credentials", "~/.ssh/id_rsa"]
    },
    "network": {
      "allowedDomains": ["github.com", "*.npmjs.org", "api.anthropic.com"],
      "deniedDomains": ["malicious.example.com"]
    }
  }
}
```

### UI & Experience

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `theme` | string | "dark" | Color theme: auto/dark/light/dark-daltonized/light-daltonized |
| `editorMode` | string | "normal" | Key bindings: normal or vim |
| `tui` | string | "fullscreen" | Terminal renderer: fullscreen or default |
| `verbose` | boolean | false | Show full tool output instead of summaries |
| `spinnerTipsEnabled` | boolean | true | Show tips while Claude is working |
| `spinnerVerbs` | object | — | Customize action verbs in spinner |
| `autoScrollEnabled` | boolean | true | Auto-scroll to bottom of output |
| `viewMode` | string | "default" | Transcript view: default/verbose/focus |
| `language` | string | — | Response language (e.g., "french", "spanish") |
| `prefersReducedMotion` | boolean | false | Reduce UI animations for accessibility |

**Example: Vim Mode + French**
```json
{
  "editorMode": "vim",
  "language": "french",
  "theme": "dark",
  "verbose": true
}
```

### Environment & Variables

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `env` | object | {} | Environment variables for all sessions |
| `defaultShell` | string | "bash" | Default shell for ! commands: bash or powershell |
| `autoUpdatesChannel` | string | "latest" | Release channel: latest or stable |
| `autoMemoryEnabled` | boolean | true | Enable auto memory accumulation |
| `autoMemoryDirectory` | string | `~/.claude/projects/<project>/memory/` | Custom auto memory location |
| `autoCompactEnabled` | boolean | true | Auto-compact when context approaches limit |

**Example: Custom Environment**
```json
{
  "env": {
    "NODE_ENV": "development",
    "MRAG_OPENAI_API_KEY": "${MRAG_OPENAI_API_KEY}",
    "PYTHONUNBUFFERED": "1"
  },
  "autoUpdatesChannel": "stable",
  "autoMemoryEnabled": true
}
```

### Skills & Extensions

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `skillListingBudgetFraction` | number | 0.01 | Context budget for skill listings (1% default) |
| `maxSkillDescriptionChars` | number | 1536 | Char cap per skill description |
| `skillOverrides` | object | {} | Per-skill visibility: on/name-only/user-invocable-only/off |
| `disableBundledSkills` | boolean | false | Disable built-in skills (bundled skills only) |

**Example: Hide Legacy Skills**
```json
{
  "skillOverrides": {
    "legacy-context": "name-only",
    "deprecated-tool": "off"
  }
}
```

### MCP (Model Context Protocol)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowedMcpServers` | object[] | — | Allowlist of MCP servers users can configure |
| `deniedMcpServers` | object[] | — | Denylist of explicitly blocked MCP servers |
| `allowManagedMcpServersOnly` | boolean | false | Only allowlist from managed settings applies |
| `enableAllProjectMcpServers` | boolean | false | Auto-approve all project .mcp.json servers |
| `enabledMcpjsonServers` | string[] | [] | Approve specific .mcp.json servers |
| `disabledMcpjsonServers` | string[] | [] | Reject specific .mcp.json servers |
| `allowClaudeAiConnectors` | boolean | true | Load claude.ai MCP connectors |
| `disableClaudeAiConnectors` | boolean | false | Disable claude.ai MCP connectors |

**Example: GitHub MCP Only**
```json
{
  "allowedMcpServers": [
    { "serverName": "github" }
  ],
  "deniedMcpServers": [
    { "serverName": "filesystem" },
    { "serverName": "shell" }
  ],
  "allowManagedMcpServersOnly": false
}
```

### Plugins & Marketplaces

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabledPlugins` | object | {} | Enable/disable per plugin: plugin-name@marketplace: true/false |
| `extraKnownMarketplaces` | object | {} | Additional plugin marketplaces to discover |
| `strictKnownMarketplaces` | object[] | — | Allowlist of approved marketplaces (managed only) |
| `strictPluginOnlyCustomization` | bool/array | — | Block skills/agents/hooks from non-plugin sources |
| `blockedMarketplaces` | object[] | — | Blocklist of marketplace sources (managed only) |
| `allowedChannelPlugins` | object[] | — | Allowlist of channel plugins that may push messages |
| `pluginTrustMessage` | string | — | Custom message in plugin trust warning |

**Example: Team Marketplace**
```json
{
  "enabledPlugins": {
    "code-formatter@team-tools": true,
    "deployer@team-tools": true
  },
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

### Hooks & Automation

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `hooks` | object | {} | Lifecycle hooks (PostToolUse, PreToolUse, etc.) |
| `disableAllHooks` | boolean | false | Disable all hooks and custom status line |
| `allowManagedHooksOnly` | boolean | false | Only managed hooks, SDK hooks, force-enabled plugins |
| `allowedHttpHookUrls` | string[] | — | Allowlist of URL patterns HTTP hooks may target |
| `httpHookAllowedEnvVars` | string[] | — | Allowlist of env vars HTTP hooks can interpolate |
| `statusLine` | object | — | Custom status line display configuration |

**Example: Ruff Linting Hook**

> **Correction (2026-06-22)**: there is no `filePattern` field — `matcher` matches the **tool name** only (regex over `Edit|Create|Write|...`), not a file path glob. Claude Code has no native per-path hook filter; the command below therefore lints the whole `src/` tree on every matching tool call, not just the file that was touched. If you need true per-file filtering, the hook command itself must read `tool_input.file_path` from the JSON Claude Code pipes to it on stdin and decide there.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Create",
        "hooks": [
          {
            "type": "command",
            "command": "ruff check src/ --select E,F,I --quiet"
          }
        ]
      }
    ]
  }
}
```

### Attribution & Git

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `attribution.commit` | string | "Co-Authored-By: Claude..." | Commit attribution |
| `attribution.pr` | string | "🤖 Generated with Claude Code" | PR attribution |
| `attribution.sessionUrl` | boolean | true | Append claude.ai session link |
| `includeGitInstructions` | boolean | true | Include git workflow in system prompt |

### Advanced Features

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `alwaysThinkingEnabled` | boolean | false | Enable extended thinking by default |
| `showThinkingSummaries` | boolean | false | Show extended thinking summaries |
| `effortLevel` | string | — | Effort level: low/medium/high/xhigh |
| `fastModePerSessionOptIn` | boolean | false | Require per-session opt-in for fast mode |
| `forceLoginMethod` | string | — | Restrict login: claudeai or console |
| `forceLoginOrgUUID` | string/array | — | Require specific organization UUID |
| `requiredMinimumVersion` | string | — | Minimum Claude Code version required |
| `requiredMaximumVersion` | string | — | Maximum Claude Code version allowed |

---

## Permission Rules Syntax

### Rule Format

```
Tool(specifier)
```

### Tool Names
- `Read` — File read operations
- `Edit` — File edit/create operations
- `WebFetch` — HTTP requests
- `Bash` — Shell commands
- `mcp__<server>__<tool>` — MCP tools

### Examples

| Rule | Matches |
|------|---------|
| `Read(./.env)` | Reading .env file |
| `Read(./.env.*)` | Reading .env.* (any variant) |
| `Edit(src/**)` | Editing anything under src/ |
| `Bash(npm run *)` | Running "npm run" commands |
| `Bash(curl *)` | Running curl commands |
| `WebFetch(domain:github.com)` | Fetching from github.com |
| `WebFetch(domain:*.example.com)` | Fetching from any subdomain |
| `mcp__github__pull_request_*` | MCP GitHub PR operations |

### Evaluation Order

Rules are processed in this order; **first match wins**:
1. `deny` rules (checked first)
2. `ask` rules
3. `allow` rules (checked last)

**Example:**
```json
{
  "permissions": {
    "deny": ["Bash(rm -rf)"],          // ← Checked first
    "ask": ["Bash(npm run deploy)"],   // ← If not denied
    "allow": ["Bash(npm run *)"]        // ← If not asked
  }
}
```
Result: `npm run build` → allow, `npm run deploy` → ask, `rm -rf` → deny

---

## Sandbox Configuration

### Filesystem Paths

**Prefix syntax:**
- `/path` — Absolute from filesystem root
- `~/path` — Relative to home directory
- `./path` or `path` — Relative to project root

**Example:**
```json
{
  "sandbox": {
    "filesystem": {
      "allowWrite": [
        "/tmp/build",        // Absolute: /tmp/build
        "~/.kube",           // Home: ~/.kube
        "./output",          // Project: ./output
        "build"              // Project (implicit): ./build
      ]
    }
  }
}
```

### Network Domains

**Wildcard syntax:**
- `example.com` — Exact domain only
- `*.example.com` — Any subdomain of example.com
- `*.*.example.com` — Any sub-subdomain

**Example:**
```json
{
  "sandbox": {
    "network": {
      "allowedDomains": [
        "github.com",           // Single
        "*.npmjs.org",          // Wildcard
        "*.internal.example.com" // Deep wildcard
      ]
    }
  }
}
```

---

## Precedence & Merge Behavior

### Scalar Values (Override)

When the same setting appears in multiple scopes, higher-priority scope wins:

```json
// ~/.claude/settings.json (User)
{ "theme": "dark" }

// .claude/settings.json (Project)
{ "theme": "light" }

// Result when running in project: theme = "light" (Project overrides User)
```

### Array Values (Merge)

Arrays concatenate and deduplicate across scopes:

```json
// ~/.claude/settings.json (User)
{
  "permissions": {
    "allow": ["Bash(npm *)"]
  }
}

// .claude/settings.json (Project)
{
  "permissions": {
    "allow": ["Bash(yarn *)"]
  }
}

// Result: ["Bash(npm *)", "Bash(yarn *)"]
```

### Special Cases

**`fallbackModel`** — Highest-priority source supplies the ENTIRE chain:
```json
// User: fallbackModel: ["sonnet", "haiku"]
// Project: fallbackModel: ["opus"]  ← wins entirely
// Result: ["opus"]
```

**`availableModels`** (managed/policy only) — Replaces lower-precedence entries:
```json
// Managed: availableModels: ["sonnet", "haiku"]
// User: availableModels: ["opus"]  ← ignored
// Result: ["sonnet", "haiku"]
```

---

## Examples

### Example 1: Secure Development Environment

```json
{
  "permissions": {
    "allow": [
      "Read(./docs/**)",
      "Read(./src/**)",
      "Edit(./src/**)",
      "Bash(npm run test)",
      "Bash(npm run lint)",
      "Bash(git *)"
    ],
    "deny": [
      "Read(./.env*)",
      "Read(./secrets/**)",
      "Bash(rm -rf /)",
      "Bash(sudo *)"
    ],
    "defaultMode": "acceptEdits"
  },
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["~/.aws/credentials", "~/.ssh"]
    },
    "network": {
      "allowedDomains": ["github.com", "*.npmjs.org", "api.anthropic.com"]
    }
  }
}
```

### Example 2: Team Collaboration

```json
{
  "env": {
    "MRAG_OPENAI_API_KEY": "${MRAG_OPENAI_API_KEY}",
    "NODE_ENV": "development"
  },
  "permissions": {
    "allow": ["Bash(npm run *)"],
    "deny": ["Bash(npm publish)"],
    "defaultMode": "plan"
  },
  "enabledPlugins": {
    "code-formatter@team-tools": true,
    "test-runner@team-tools": true
  },
  "extraKnownMarketplaces": {
    "team-tools": {
      "source": {
        "source": "github",
        "repo": "publicis-corp/claude-plugins"
      }
    }
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "ruff check src/ --select E,F,I"
          }
        ]
      }
    ]
  }
}
```

### Example 3: Enterprise Deployment

```json
{
  "forceLoginMethod": "claudeai",
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "requiredMinimumVersion": "2.1.150",
  "permissions": {
    "allow": [
      "Bash(npm run *)",
      "Read(~/company-docs/**)"
    ],
    "deny": [
      "Read(./.env*)",
      "Bash(curl *)",
      "WebFetch()"
    ],
    "defaultMode": "default"
  },
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "filesystem": {
      "denyRead": ["~/.ssh", "~/.aws", "/etc/passwd"]
    }
  },
  "allowManagedMcpServersOnly": true,
  "allowManagedHooksOnly": true,
  "strictPluginOnlyCustomization": ["skills", "hooks"]
}
```

---

## Verify Your Configuration

### Check Active Settings
```bash
claude /status
```
Shows which settings scopes are loaded.

### Diagnose Configuration Issues
```bash
claude /doctor
```
Lists invalid entries with sources and field details.

### Debug Specific Setting
```bash
claude /config key=value
```
Change single option without opening full interface.

---

## See Also

*(Corrected 2026-08-06 — the two links this section used to carry,
`claude-code-memory.md` and `claude-code-permissions.md`, don't exist as separate files.)*

- [Claude Code Advanced Config](./claude-code-advanced-config.md) — subagents, skills, hooks, memory
- [Claude Code MCP Setup](./claude-code-mcp-setup.md)
- [Claude Code Enterprise Deployment](./claude-code-enterprise-deployment.md)
