# Claude Code MCP (Model Context Protocol) Setup

Complete guide to Model Context Protocol configuration, integration, and governance for Claude Code.

> **Corrected 2026-08-06** (documentation-utility pass): this is generic MCP reference material,
> not a description of this project's own configuration. In particular, the section that used
> to be titled "Built-in MCP Servers" implied GitHub/Slack/Filesystem/Anthropic-Docs servers
> ship pre-configured with Claude Code — they don't; every one of them still needs the same
> `.mcp.json` setup steps as any other server, which is exactly what that section's own "Setup:"
> instructions already showed, one paragraph below the misleading heading. Retitled below.
> Confirmed via `.claude/settings.json`'s own note: **this project does not currently define
> any MCP server** — nothing in this file describes an active integration here.

**Table of Contents**
1. [MCP Overview](#mcp-overview) — What is MCP
2. [MCP Storage](#mcp-storage) — Where configs live
3. [Example MCP Server Configurations](#example-mcp-server-configurations) — GitHub, Slack, etc. — none pre-installed, all require the setup steps shown
4. [Configuration by Scope](#configuration-by-scope) — User vs Project
5. [MCP Governance](#mcp-governance) — Security & approval
6. [Examples](#examples) — Real-world setups

---

## MCP Overview

### What is MCP?

**Model Context Protocol** allows Claude Code to interact with external systems through standardized tools:
- **Integrations**: GitHub, Slack, GitLab, Jira, etc.
- **File systems**: Local filesystem, S3, cloud storage
- **Databases**: SQL, vector stores, knowledge graphs
- **APIs**: REST, GraphQL, webhooks

MCP runs in a **sandbox** separate from Claude Code, so integrations don't compromise security.

### When to Use MCP

✅ **Use MCP for:**
- Querying external APIs (GitHub issues, Slack messages)
- Interacting with services you already use
- Adding context from multiple systems

❌ **Don't use MCP for:**
- Local file operations (use built-in Read/Edit tools)
- Bash commands (use built-in Bash tool)
- Simple HTTP requests (use WebFetch)

---

## MCP Storage

### Files & Locations

| File | Scope | Contains | Shared |
|------|-------|----------|--------|
| `~/.claude.json` | User | MCP servers for all projects | No — per machine |
| `.mcp.json` | Project | MCP servers for this repo | Yes — in git |
| `~/.claude/CLAUDE.md` | User | MCP-related notes | No |
| `.claude/CLAUDE.md` | Project | MCP setup docs | Yes — in git |

### ~/.claude.json (User Scope)

Stores personal MCP servers available in every project:

```json
{
  "mcpServers": {
    "github": {
      "command": "node",
      "args": ["/opt/mcp/github/index.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "slack": {
      "command": "python3",
      "args": ["/opt/mcp/slack/server.py"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    }
  }
}
```

### .mcp.json (Project Scope)

Stores MCP servers specific to this repository:

```json
{
  "mcpServers": {
    "anthropic-docs": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/docs-mcp"],
      "description": "Browse Anthropic documentation"
    },
    "project-context": {
      "command": "python3",
      "args": ["./tools/mcp-server.py"],
      "env": {
        "PROJECT_ROOT": "${CLAUDE_PROJECT_DIR}"
      },
      "description": "Project-specific context server"
    }
  }
}
```

---

## Built-in MCP Servers

Claude Code provides several built-in MCP integrations:

### GitHub

**Tools**: List/search issues, create issues, read PRs, push commits, create PRs

**Setup**:
1. Generate GitHub personal access token (Settings → Developer settings → Personal access tokens)
2. Store in environment: `export GITHUB_TOKEN=ghp_...`
3. Enable in settings: `"enableAllProjectMcpServers": true`

**Example Use**:
```
Pull up PR #42 from this repo
List all open issues labeled "bug"
Create a new issue for tomorrow's task
```

### Slack

**Tools**: Send messages, post threads, upload files, search conversation history

**Setup**:
1. Create Slack bot (Your Apps → Create New App)
2. Add scopes: `chat:write`, `files:upload`, `search:read`
3. Generate bot token: `xoxb-...`
4. Store: `export SLACK_BOT_TOKEN=xoxb_...`

**Example Use**:
```
Send code review update to #engineering
Post debugging output to thread
Search for previous error messages
```

### Filesystem

**Tools**: List files, read files, write files, create directories

**Warning**: ⚠️ Filesystem MCP provides direct file access. Use `permissions.deny` to restrict paths.

**Configuration**:
```json
{
  "deniedMcpServers": [
    { "serverName": "filesystem" }
  ]
}
```

### Anthropic Docs

**Tools**: Search documentation, fetch specific pages

**Setup**: Install via npm automatically

**Example Use**:
```
Search documentation for "streaming API"
Find examples of prompt caching
```

---

## Configuration by Scope

### User-Level MCP (.claude.json)

Used by Claude Code in every project on your machine.

**When to configure here:**
- Services you use in all projects (GitHub, Slack)
- Personal integrations (your custom LLM, vector DB)
- General-purpose tools

**Example**:
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "personal-tools": {
      "command": "python3",
      "args": ["~/.claude/mcp-servers/personal.py"],
      "env": {
        "PERSONAL_API_KEY": "${PERSONAL_API_KEY}"
      }
    }
  }
}
```

### Project-Level MCP (.mcp.json)

Used only in this repository; committed to git and shared with team.

**When to configure here:**
- Project-specific integrations (Jira, internal tools)
- Tools built for this codebase
- Team-wide services (company Slack, internal docs)

**Example**:
```json
{
  "mcpServers": {
    "qdrant": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-qdrant"],
      "env": {
        "QDRANT_URL": "http://localhost:6333"
      },
      "description": "Vector store for RAG queries"
    },
    "internal-api": {
      "command": "python3",
      "args": ["./tools/internal-api-mcp.py"],
      "env": {
        "API_BASE": "https://api.internal.example.com",
        "API_TOKEN": "${INTERNAL_API_TOKEN}"
      },
      "description": "Company internal API"
    }
  }
}
```

### Per-Session MCP (--mcp-config)

Override for a single session:

```bash
claude --mcp-config /path/to/custom-mcp.json
```

---

## MCP Governance

### Security Review Checklist

Before deploying an MCP server, review:

| Criterion | Question | Status |
|-----------|----------|--------|
| **Source** | Is MCP from Anthropic, official org, or vetted? | ✅/❌ |
| **Capabilities** | What does it access? (files, network, APIs) | ✅/❌ |
| **Secrets** | How are credentials passed? (env vars, secure?) | ✅/❌ |
| **Audit** | Are actions logged? Can we see what it did? | ✅/❌ |
| **Scope** | Is it restricted to safe paths/domains? | ✅/❌ |
| **Approval** | Team lead + security sign-off | ✅/❌ |

### Permission Rules for MCP

Restrict MCP tool usage with `permissions.deny`:

```json
{
  "permissions": {
    "allow": [
      "mcp__github__get_issue",
      "mcp__github__list_issues"
    ],
    "deny": [
      "mcp__github__push_commit",   // Block direct commits
      "mcp__filesystem__write",      // Block filesystem writes
      "mcp__slack__upload_file"      // Block file uploads
    ]
  }
}
```

### Managed MCP (Enterprise)

For organization-wide MCP governance:

**managed-settings.json**:
```json
{
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverName": "slack" }
  ],
  "deniedMcpServers": [
    { "serverName": "filesystem" }
  ],
  "allowManagedMcpServersOnly": true
}
```

**Effect:**
- ✅ Only GitHub and Slack servers allowed
- ❌ Filesystem blocked entirely
- ❌ Users cannot add custom servers

---

## Environment Variables

### Common MCP Environment Variables

| Var | Used By | Example |
|-----|---------|---------|
| `GITHUB_TOKEN` | GitHub MCP | `ghp_1234567890abcdef` |
| `SLACK_BOT_TOKEN` | Slack MCP | `xoxb_1234567890_1234567890_abcdefghij` |
| `ANTHROPIC_API_KEY` | Anthropic services | `sk-ant-v0-...` |
| `CLAUDE_PROJECT_DIR` | Any MCP | `${CLAUDE_PROJECT_DIR}` |

### Secure Storage (Linux/macOS)

```bash
# Store in system keychain
security add-generic-password -s "GitHub Token" -a "claude" -w "ghp_..."

# Retrieve in ~/.claude.json
{
  "mcpServers": {
    "github": {
      "env": {
        "GITHUB_TOKEN": "$(security find-generic-password -s 'GitHub Token' -a 'claude' -w)"
      }
    }
  }
}
```

### Environment in settings.json

```json
{
  "env": {
    "GITHUB_TOKEN": "${GITHUB_TOKEN}",
    "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
    "QDRANT_URL": "http://localhost:6333"
  }
}
```

---

## Writing Custom MCP Servers

### Simple Node.js Example

**tools/mcp-server.js**:
```javascript
#!/usr/bin/env node
// Custom MCP server for project context

const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { TextContent, Tool } = require('@modelcontextprotocol/sdk/types.js');

const server = new Server({
  name: 'project-context',
  version: '1.0.0',
});

server.setRequestHandler(Tool.ListRequest, async () => ({
  tools: [
    {
      name: 'get_project_config',
      description: 'Read project configuration',
      inputSchema: {
        type: 'object',
        properties: {}
      }
    }
  ]
}));

server.setRequestHandler(Tool.CallRequest, async (request) => {
  if (request.params.name === 'get_project_config') {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(require('./project.json'), null, 2)
        }
      ]
    };
  }
  throw new Error('Unknown tool');
});

const transport = new StdioServerTransport();
server.connect(transport);
```

**Configure in .mcp.json**:
```json
{
  "mcpServers": {
    "project-context": {
      "command": "node",
      "args": ["./tools/mcp-server.js"]
    }
  }
}
```

### Simple Python Example

**tools/mcp_server.py**:
```python
#!/usr/bin/env python3
# Custom MCP server for vector queries

import json
import sys
from typing import Any

class MCPServer:
    def __init__(self):
        self.tools = [
            {
                "name": "query_vectors",
                "description": "Query vector store",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "default": 5}
                    }
                }
            }
        ]

    def handle_list_tools(self):
        return {"tools": self.tools}

    def handle_call_tool(self, name: str, args: dict):
        if name == "query_vectors":
            query = args.get("query")
            k = args.get("k", 5)
            # Query your vector store
            results = self.query_qdrant(query, k)
            return {
                "content": [{"type": "text", "text": json.dumps(results)}]
            }
        raise ValueError(f"Unknown tool: {name}")

    def query_qdrant(self, query: str, k: int):
        # Connect to Qdrant and query
        return [{"id": i, "score": 0.95 - (i*0.05)} for i in range(k)]

    def run(self):
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            
            message = json.loads(line)
            if message["method"] == "tools/list":
                response = self.handle_list_tools()
            elif message["method"] == "tools/call":
                response = self.handle_call_tool(
                    message["params"]["name"],
                    message["params"]["arguments"]
                )
            
            print(json.dumps({"id": message.get("id"), "result": response}))
            sys.stdout.flush()

if __name__ == "__main__":
    server = MCPServer()
    server.run()
```

**Configure in .mcp.json**:
```json
{
  "mcpServers": {
    "vector-query": {
      "command": "python3",
      "args": ["./tools/mcp_server.py"],
      "env": {
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

---

## Examples

### Example 1: GitHub-Focused Setup

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

**Use cases:**
- "List all open issues in this repo"
- "Create a PR for the feature branch"
- "Show me the last 5 commits"

### Example 2: Team Collaboration Setup

**.mcp.json**:
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"
      }
    },
    "qdrant": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-qdrant"],
      "env": {
        "QDRANT_URL": "http://localhost:6333"
      }
    }
  }
}
```

**.claude/settings.json**:
```json
{
  "enableAllProjectMcpServers": true,
  "permissions": {
    "allow": [
      "mcp__github__get_issue",
      "mcp__github__list_issues",
      "mcp__slack__send_message",
      "mcp__qdrant__search"
    ],
    "deny": [
      "mcp__github__push_commit",
      "mcp__slack__upload_file"
    ]
  }
}
```

### Example 3: Enterprise Setup

**managed-settings.json**:
```json
{
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverName": "slack" },
    { "serverName": "jira" }
  ],
  "deniedMcpServers": [
    { "serverName": "filesystem" },
    { "serverName": "shell" }
  ],
  "allowManagedMcpServersOnly": true
}
```

**Effect:** Only GitHub, Slack, Jira allowed. Filesystem and shell MCP blocked organization-wide.

---

## Troubleshooting

### MCP Server Not Found

**Error**: "MCP server 'github' not found"

**Solutions**:
1. Check `.mcp.json` exists and is valid JSON
2. Verify server command is installed: `which npx`, `which python3`
3. Run `claude /doctor` to see configuration errors

### Environment Variables Not Loading

**Error**: "GITHUB_TOKEN not set"

**Solutions**:
1. Verify env var in shell: `echo $GITHUB_TOKEN`
2. Check `.mcp.json` references it: `"GITHUB_TOKEN": "${GITHUB_TOKEN}"`
3. Store in `.env.local` and source it: `source .env.local` before running claude

### Permission Denied

**Error**: "Tool 'mcp__github__push_commit' denied"

**Solutions**:
1. Check `permissions.deny` rules in settings.json
2. Verify tool name format: `mcp__<server>__<tool>`
3. Use `permissions.allow` to explicitly permit

---

## See Also

- [Claude Code Settings Reference](./claude-code-settings-reference.md)
- [Claude Code Plugins & Marketplaces](./claude-code-plugins-marketplaces.md)
- [Claude Code Enterprise Deployment](./claude-code-enterprise-deployment.md)
- [Anthropic MCP Documentation](https://modelcontextprotocol.io/)
