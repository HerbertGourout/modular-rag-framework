# MCP Integration Guide

This guide explains how to securely integrate external tools via Model Context Protocol (MCP) servers with Claude Code on the Modular RAG Framework.

---

## What is MCP?

Model Context Protocol (MCP) allows Claude Code to interact with external systems—databases, APIs, tools, file systems—via a standardized protocol. Each MCP integration represents a **new security boundary** and must be reviewed before deployment.

**Why this matters**: MCP servers can access files, execute commands, and retrieve data from external systems. We use a structured **security review process** to ensure integrations are safe, auditable, and scoped appropriately.

---

## Security Review Process

### Step 1: Request an MCP Integration

**Who**: Any team member can request an MCP integration.  
**Where**: Create an issue on GitLab in the `modular-rag-framework` project.  
**Template**:

```markdown
## MCP Integration Request

**Server Name**: [e.g., postgresql-query-tool, elasticsearch-search]

**Purpose**: [What problem does this MCP solve? e.g., "Query our production database for analytics"]

**Vendor/Source**: [Where is this MCP from? Official vendor, OSS repo, custom?]

**Repository**: [Link to MCP source code, if available]

**Proposed Scope**: [Which paths can this MCP access? e.g., tests/, examples/, src/]

**Proposed Capabilities**: [What operations? read_file, execute_command, query_database?]

**Security Considerations**: [Any sensitive data involved? How are secrets managed?]

---
## Approval will follow the Security Review Checklist below.
```

### Step 2: Security Review Checklist

Review team (Architecture + Security) must sign off on ALL criteria:

| Criterion | Question | Status | Notes |
|-----------|----------|--------|-------|
| **Source** | Is the MCP from a trusted vendor (Anthropic, major OSS project) or vetted internal team? | ✅/❌ | |
| **Capabilities** | What file/command operations does it grant? (read-only vs read-write) | ✅/❌ | |
| **Secrets** | Does the MCP require API keys, credentials? How are they passed? | ✅/❌ | Must use env vars, never hardcoded |
| **Audit** | Are MCP actions logged? Can we trace what was accessed/modified? | ✅/❌ | Must have audit trail |
| **Scope** | Is the MCP restricted to safe folders? (tests/, examples/, src/ safe; manifests/production/ blocked) | ✅/❌ | Fail if unrestricted access |
| **Secrets Management** | If secrets needed, are they stored in VS Code secrets or .env (gitignored)? | ✅/❌ | Never commit secrets |
| **Approval** | Has security team approved this integration? Signed in issue. | ✅/❌ | Approval comment required |

**Example approval checklist** (filled):

```markdown
## Security Review Checklist

- [x] Source: Anthropic's official repository
- [x] Capabilities: read_file (tests/, examples/ only), no write access
- [x] Secrets: Uses VS Code built-in secret storage (no env vars needed)
- [x] Audit: MCP logs all file accesses to .vscode/output
- [x] Scope: Restricted to tests/ and examples/ (see denyPaths below)
- [x] Secrets Management: N/A (no external API keys)
- [x] Approval: @security-team approved on 2026-06-20

## Approved for deployment
```

### Step 3: Scope Definition

Define **exactly** which paths the MCP can access. This is internal governance bookkeeping for the review process — `enabled`/`allowPaths`/`denyPaths`/`capabilities`/`audit` are not real `.mcp.json` fields (see the correction in Step 4); record them here, then translate the *capabilities* into actual `permissions.allow`/`ask`/`deny` rules in `.claude/settings.json` if the MCP's tools need scoping:

```json
{
  "mcpServers": {
    "new-mcp-tool": {
      "enabled": true,
      "allowPaths": [
        "tests/**",
        "examples/**"
      ],
      "denyPaths": [
        "**/.env*",
        "manifests/production/**",
        ".claude/rules/**",
        "src/modular_rag/security/**"
      ],
      "capabilities": ["read_file"],
      "audit": "All file accesses logged to .vscode/output"
    }
  }
}
```

**Path rules**:
- ✅ **allowPaths** (whitelist): MCP can access ONLY these paths
- ❌ **denyPaths** (blacklist): MCP can NEVER access these paths
- **Collision rule**: If a path matches both allow and deny, DENY wins (fail-safe)

### Step 4: Integration into .mcp.json

> **Correction (2026-06-22)**: MCP servers are configured in a **`.mcp.json` file at the project root**, not inside `.claude/settings.json`. `mcpServers` is not a recognized key in `settings.json` — Claude Code only reads it from `.mcp.json`. The `allowPaths`/`denyPaths`/`scope`/`approvedDate` fields below are this project's own governance metadata (useful for the review process and audit trail), not fields Claude Code itself understands — Claude Code's real `.mcp.json` entry shape is just `command`/`args`/`env` (for a local `stdio` server) or `type`/`url` (for a remote `http`/`sse` server). Keep the governance metadata in this guide's "Current MCP Integrations" section below instead of inventing extra JSON keys.

Once approved, add the MCP to a project-root `.mcp.json`:

```json
{
  "mcpServers": {
    "your-mcp-name": {
      "command": "npx",
      "args": ["-y", "@some-vendor/mcp-server"],
      "env": {}
    }
  }
}
```

Then record the governance metadata (vendor, approval date, scope, capabilities, audit notes) in the "Current MCP Integrations" section of this guide — not in JSON.

### Step 5: Documentation

Add entry to this guide's **Current Integrations** section (see below).

---

## Current MCP Integrations

### None Approved Yet

This section lists all approved MCPs for the Modular RAG Framework.

**Template for approved MCPs:**

```markdown
### MCP Name

- **Vendor**: [Company/OSS]
- **Purpose**: [One-liner]
- **Enabled**: Yes/No
- **Scope**: tests/, examples/
- **Capabilities**: read_file
- **Audit**: [Trail location]
- **Approved**: [Date] by [Team]
- **Issues**: [Link to approval issue]
- **Notes**: [Any considerations]

**Example usage**:
\`\`\`
# Claude can access files in tests/ and examples/
# Queries like "read tests/unit/test_retriever.py" work
# Queries like "read src/modular_rag/core/models.py" are blocked
\`\`\`
```

---

## Guidelines for New MCP Requests

### ✅ Good Candidates for MCP Integration

- **Read-only tools**: File readers, query tools, documentation browsers
- **Logging tools**: Audit trails, debugging output analyzers
- **Safe namespaces**: tests/, examples/, docs/ (low risk)
- **Build tools**: Linters, test runners, documentation generators

**Example**: "Read test output files to help debug test failures"
```
Request: File reader MCP for tests/ and examples/
Approval: Easy (read-only, safe namespaces)
```

### ❌ High-Risk Candidates (Likely Blocked)

- **Write access to production**: src/modular_rag/core/, src/modular_rag/security/
- **Secret access**: Any MCP that reads .env or credentials
- **CI/CD pipeline**: Access to .gitlab-ci.yml or deployment configs
- **Unrestricted file system**: "All files" scope
- **Unauditable**: MCP with no logging

**Example**: "Database query tool with write access to production DB"
```
Request: PostgreSQL query MCP with write access
Approval: REJECTED (production scope, write access, high risk)
Remedy: Request read-only scope on dev/staging databases only
```

---

## Troubleshooting MCP Issues

### Issue: MCP Not Working

1. Check `.claude/settings.json`:
   - Is `"enabled": true`?
   - Does allowPaths match your file location?
   - Does denyPaths block your query?

2. Check VS Code output:
   - Open View → Output → look for MCP logs
   - Is the MCP process running?

3. Check permissions:
   - Does your file path match allowPaths?
   - Are you querying a blocked path (denyPaths)?

### Issue: "Access Denied" Error

1. Verify your file path is in **allowPaths**:
   ```
   ✅ tests/unit/test_chunker.py (allowed if allowPaths includes tests/)
   ❌ src/modular_rag/security/policy.py (blocked — security module)
   ```

2. Check **denyPaths** (deny wins over allow):
   ```json
   {
     "allowPaths": ["src/**"],
     "denyPaths": [".env*", "src/modular_rag/security/**"]
   }
   ```
   - ❌ src/modular_rag/security/policy.py → BLOCKED (denyPath matches)
   - ✅ src/modular_rag/ingestion/chunker.py → ALLOWED (allowPath matches, no denyPath match)

### Issue: Secrets Exposure

If MCP needs API keys:
1. Store in VS Code built-in secret storage (Settings → Secrets)
2. OR use .env with explicit denyPath on `.env*`
3. NEVER hardcode credentials in .claude/settings.json

---

## Approval Template

Copy this into your GitLab issue once security review is complete:

```markdown
## ✅ MCP APPROVED

Approved by @security-team on [DATE]

### Approval Details

- [x] Source verified: [Vendor]
- [x] Capabilities scoped: [Operations]
- [x] Audit trail: [Location]
- [x] denyPaths configured: [Paths blocked]
- [x] allowPaths configured: [Paths allowed]
- [x] No secrets exposure risk

### Next Steps

1. Add to `.claude/settings.json` (see configuration below)
2. Add entry to docs/guides/mcp-integrations.md
3. Create branch and commit
4. Close this issue after deployment

### Configuration

\`\`\`json
{
  "mcpServers": {
    "mcp-name": {
      "enabled": true,
      "allowPaths": [...],
      "denyPaths": [...]
    }
  }
}
\`\`\`
```

---

## References

- **Security Design**: See [.claude/rules/security-layers.md](../../.claude/rules/security-layers.md#layer-06-mcp-governance)
- **VS Code Secrets**: [VS Code Secret Storage Docs](https://code.visualstudio.com/api/working-with-extensions/common-capabilities)
- **MCP Specification**: [Anthropic MCP Protocol](https://modelcontextprotocol.io/)
- **Project Security**: See [CONTRIBUTING.md](../../CONTRIBUTING.md) Git Workflow section
