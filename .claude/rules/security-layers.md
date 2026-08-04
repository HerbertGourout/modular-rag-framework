# Security Strategy: 7-Layer Defense

This document defines the complete security architecture for Claude Code interactions with the Modular RAG framework. Seven layers of defense work in concert to protect the codebase integrity, secrets, and compliance boundaries.

---

## Layer 01: Permissions — First Line of Control

**Definition**: Globally defines what is possible. Granular per-path permission model in `.claude/settings.json`.

### 3-Bucket Model (real Claude Code permission system)

Claude Code uses **three buckets**, not four tiers. The old `dontAsk`/`acceptEdits`/`ask_before_edit` terminology was invented and never read by the tool. The real model:

```
deny  → always blocked, no prompt (highest priority)
  ↓
ask   → prompts every time before acting
  ↓
allow → auto-approved, no prompt
  ↓
(everything else falls to defaultMode — "default" in this project)
```

**Configuration**: `.claude/settings.json` → `permissions.deny` / `permissions.ask` / `permissions.allow` arrays of `Edit(path/**)` / `Write(path/**)` / `Read(path/**)` patterns.

### deny — Always Blocked

| Path | Reason |
|------|--------|
| `**/.env*` | Secrets — API keys, credentials, tokens |
| `**/*.local.md` | User-specific configuration |
| `manifests/production/**` | Production configs (V4+ scope) |
| `.gitlab/**` | CI/CD pipeline configuration |
| `src/modular_rag/adapters/auth/**` | Not yet assigned a capability per ADR-0005; revisit at Lot 11b |
| `benchmarks/**` | Benchmarks (V3+ scope) |

**Changed 2026-08-04 (ADR-0005, Lot 2):** `.claude/rules/**` and
`src/modular_rag/adapters/{llms,graphstores,search}/**` moved from `deny` to `ask` below — they
are no longer "V2+/V3+ reserved" native-build stubs but reachable engine-delegation adapter
targets (`docs/refactoring-plan.md` Lots 6/7/15). `adapters/auth/**` stays denied — see reason
above.

### allow — Auto-Approved (no prompt)

| Path | Rationale |
|------|-----------|
| `tests/**` | Test creation encouraged; no risk to core |
| `examples/**` | Safe sandbox; demonstrates framework use |
| `docs/**` | Documentation changes never break code |
| `src/modular_rag/ingestion/**` | New chunkers, parsers, processors safe |
| `src/modular_rag/retrieval/**` | New retrievers, rerankers safe |
| `src/modular_rag/generation/**` | New generators, prompt templates safe |
| `src/modular_rag/eval/**` | New metrics, scorers safe |
| `src/modular_rag/memory/**` | Context/conversation extensions safe |

### ask — Prompts Every Time

| Path | Rationale |
|------|-----------|
| `.claude/rules/**` | Architecture rules — breaking changes; moved from deny 2026-08-04 so Lot 2-style realignments are possible with confirmation |
| `src/modular_rag/contracts/**` | Protocol definitions — breaking changes propagate everywhere |
| `src/modular_rag/orchestration/**` | Registry, engine, router changes need approval |
| `src/modular_rag/security/**` | Policies, guards, redaction rules need review |
| `src/modular_rag/adapters/embeddings/**` | Embedding protocol implementations protected |
| `src/modular_rag/adapters/vectorstores/**` | Vector store binding implementations protected |
| `src/modular_rag/adapters/llms/**` | Engine-delegation adapter target (Lots 6/7/15) — protected, not blocked |
| `src/modular_rag/adapters/graphstores/**` | Engine-delegation adapter target (Lots 6/7/15) — protected, not blocked |
| `src/modular_rag/adapters/search/**` | Engine-delegation adapter target (Lots 6/7/15) — protected, not blocked |
| `src/modular_rag/core/**` | Core models, exceptions, utilities protected |
| `pyproject.toml` | Dependencies, versions, build config protected |
| `CONTRIBUTING.md` | Development guidelines protected |
| `.gitlab-ci.yml` | CI/CD pipeline protected |

---

## Layer 02: Hooks — Contextual Control at Runtime

**Definition**: Second line of defense. Runtime validation of actions before execution.

### PostToolUse Hooks (After File Write)

**Purpose**: Catch syntax errors, import violations, and code quality issues immediately.

```json
{
  "PostToolUse": [
    {
      "matcher": "Edit|Write",
      "hooks": [
        {
          "type": "command",
          "command": "PATH=\"$HOME/.local/bin:$PATH\" ruff check src/modular_rag/ tests/ --select E,F,I --ignore E501 --quiet"
        }
      ]
    }
  ]
}
```

**What it validates**:
- **E** — Syntax errors (indentation, duplicate keys)
- **F** — Undefined names (missing imports, typos)
- **I** — Import ordering (alphabetical, grouped by type)

**When it runs**: After every Edit or Write tool call. Note: `matcher` matches the **tool name** (`Edit|Write`), not file paths — there is no native per-path hook filter. The hook therefore lints the entire `src/modular_rag/` + `tests/` tree on every Edit/Write regardless of which file changed.

### Reserved Validation Ideas (not in settings.json — backlog only)

These checks would be valuable but require external scripts — no `futureHooks` key exists in Claude Code:

- Cross-domain import detection (`retrieval/` never imports from `generation/`)
- Protocol conformance checking (implementations match contracts/)
- Lazy import validation (heavy deps inside function, not at module level)

Use the `/validate-security` and `/validate-architecture` skills for manual versions today.

---

## Layer 03: CLAUDE.md & Project Policies — Expected Behaviors

**Definition**: Business rules, sensitive areas, and project boundaries documented.

### CLAUDE.md Blocks

| Block | Content | Sensitivity |
|-------|---------|-------------|
| 01 | Project purpose (V1-V5 progression, non-negotiables) | 🔴 CRITICAL |
| 02 | Architecture rules (hexagonal layering, direction of flow) | 🔴 CRITICAL |
| 03 | Project structure (folder layout, responsibilities) | 🟡 MEDIUM |
| 04 | Development commands (quick/full/integration/e2e validation) | 🟡 MEDIUM |
| 05 | Coding rules (contracts first, no cross-domain, manifests) | 🔴 CRITICAL |
| 06 | Testing and validation (scopes, markers, expectations) | 🟡 MEDIUM |
| 07 | Security rules (never import between domains, Safety ≠ Security) | 🔴 CRITICAL |
| 08 | Git and PR workflow (branch naming, MR checklist) | 🟡 MEDIUM |
| 09 | Roadmap — owned (native) vs. delegated (external engine) per ADR-0005 | 🔴 CRITICAL |

### Domain-Specific CLAUDE.md Files

**Purpose**: Module-level guidance for sensitive domains.

| File | Domain | Key Rules |
|------|--------|-----------|
| `src/modular_rag/security/CLAUDE.md` | Security module | Safety ≠ Security; PII patterns; risk scoring; never log full text |
| `src/modular_rag/contracts/CLAUDE.md` | Contract layer | Protocol first; no implementation details; extend docs with ADR |
| `src/modular_rag/orchestration/CLAUDE.md` | Orchestration | Registry pattern only; manifest-driven; never direct Python wiring |

### Policy Documents

| Document | Purpose |
|----------|---------|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development workflow, branch strategy, MR checklist |
| [docs/guides/validation.md](../../docs/guides/validation.md) | Validation command reference |
| [docs/adr/](../../docs/adr/) | Architectural decisions (versions, contracts, security) |

---

## Layer 04: Folder Segmentation — Strict Write Boundaries

**Definition**: Write permissions are restricted by project area and workload.

### Segmentation Strategy

```
src/modular_rag/
├── cli/                      ← API entry point (restricted)
├── api/                      ← REST handlers (restricted)
├── app/                      ← Bootstrap, settings (restricted)
├── orchestration/            ← Registry, engine, wiring (ask)
├── contracts/                ← Protocol definitions (ask)
├── core/                     ← Models, exceptions, utilities (ask)
├── adapters/
│   ├── embeddings/           ← Embedding implementations (ask)
│   ├── vectorstores/         ← Vector store bindings (ask)
│   ├── llms/                 ← Engine-delegation adapter target (ask, Lots 6/7/15)
│   ├── graphstores/          ← Engine-delegation adapter target (ask, Lots 6/7/15)
│   ├── search/               ← Engine-delegation adapter target (ask, Lots 6/7/15)
│   ├── auth/                 ← Auth adapters (BLOCKED — not yet assigned, revisit Lot 11b)
│   └── ...
├── security/                 ← Filters, policies, guards (ask)
├── ingestion/                ← Chunkers, parsers (allow)
├── retrieval/                ← Retrievers, rerankers (allow)
├── generation/               ← Generators, prompts (allow)
├── eval/                     ← Metrics, scorers (allow)
├── memory/                   ← Context, conversation (allow)
└── agents/                   ← Agent protocols (ask)

tests/
├── unit/                     ← Unit tests (allow)
├── integration/              ← Integration tests (allow)
├── contract/                 ← Protocol conformance tests (allow)
└── e2e/                      ← End-to-end tests (allow)

docs/
├── adr/                      ← Architectural decisions (allow)
├── architecture/             ← Architecture docs (allow)
├── guides/                   ← Developer guides (allow)
└── reviews/                  ← Review notes (allow)

manifests/
├── presets/                  ← Reference configs (allow)
├── dev/                      ← Dev configs (BLOCKED until V2)
├── staging/                  ← Staging configs (BLOCKED until V4)
└── production/               ← Production configs (BLOCKED until V4)

examples/
├── simple_qa/                ← V1 reference example (allow)
├── agentic_rag/              ← V2+ example (BLOCKED — V2 scope)
├── graph_memory/             ← V3+ example (BLOCKED — V3 scope)
└── ...                       ← Others (BLOCKED)
```

### Rationale

- **Blocked zone** (auth/ only, as of 2026-08-04): not yet assigned a capability by ADR-0005
- **Ask-before zones** (contracts/, orchestration/, security/, llms/, graphstores/, search/,
  `.claude/rules/`): changes here propagate to the entire framework, or (for the three adapter
  dirs) are engine-delegation targets that need confirmation rather than a hard block
- **Allow zones** (ingestion/, retrieval/, generation/): New implementations are localized, safe
- **Allow zones** (tests/, examples/, docs/): Zero friction on documentation and testing

---

## Layer 05: Secret Management — No Hardcoding, Full Block

**Definition**: Secrets are never embedded in code, committed, or exposed to the model.

### What Counts as a Secret

| Type | Examples | Risk | Handling |
|------|----------|------|----------|
| **API Keys** | `MRAG_OPENAI_API_KEY`, `HUGGINGFACE_TOKEN` | 🔴 CRITICAL | Never commit; use `.env` |
| **Credentials** | Database passwords, OAuth tokens | 🔴 CRITICAL | Never commit; use `.env` |
| **Connection Strings** | `MRAG_QDRANT_URL` with auth | 🔴 CRITICAL | Use environment variable |
| **Encryption Keys** | Private keys, encryption secrets | 🔴 CRITICAL | Use key management service |
| **PII** | SSN, credit card numbers, phone | 🔴 CRITICAL | Use security/redaction/ |

### .env Management

**File**: `.env` (gitignored — never committed)

**Purpose**: Local development only. Contains user-specific values.

**Example** (`.env.example` — commits this as template):
```bash
# Required for development
MRAG_OPENAI_API_KEY=sk-...          # Your OpenAI API key
MRAG_QDRANT_URL=http://localhost:6333  # Local Qdrant instance
MRAG_QDRANT_TIMEOUT=30              # Connection timeout in seconds

# Optional for advanced features
MRAG_LOG_LEVEL=INFO                 # Logging verbosity
MRAG_ENVIRONMENT=development         # environment (development|staging|production)

# Security — used in tests only
MRAG_TEST_MODE=true                 # Enable test safety measures
```

**Setup (each developer)**:
```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your values
export MRAG_OPENAI_API_KEY=sk-your-key-here

# 3. Load in shell (bash)
set -o allexport
source .env
set +o allexport
```

### Code Patterns for Secrets

**❌ NEVER DO THIS:**
```python
# Hardcoded secret
API_KEY = "sk-12345"

# Exposed in logs
logger.info(f"Connecting with key={api_key}")

# Committed to git
.env or config.json with values
```

**✅ ALWAYS DO THIS:**
```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env

# From environment
API_KEY = os.getenv("MRAG_OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("MRAG_OPENAI_API_KEY not set in .env")

# Never log secrets
logger.info(f"Connecting to OpenAI (key: {API_KEY[:6]}...)")  # Partial exposure only
```

### .gitignore Enforcement

**Secrets blocked**:
```gitignore
.env               # Environment variables
.env.local         # User overrides
.env.*.local       # Environment-specific secrets
*.pem              # Private keys
*.key              # Encryption keys
secrets/           # Entire secrets folder
credentials/       # Credentials folder
```

**Rationale**: One-layer-deep pattern matching ensures all variants are caught.

---

## Layer 06: MCP Governance — Security Review of External Integration

**Definition**: Model Context Protocol (MCP) servers are reviewed before integration.

### What is MCP?

MCP allows Claude Code to interact with external tools, databases, and systems via standardized protocol. Each integration represents a new security boundary.

### MCP Review Checklist

Before using any MCP server integration, security review must cover:

| Criterion | Question | Status |
|-----------|----------|--------|
| **Source** | Is the MCP server from a trusted vendor? (Anthropic, major OSS) | ✅/❌ |
| **Capabilities** | What file operations does it grant? (read-only vs write) | ✅/❌ |
| **Secrets** | Does the MCP server require API keys? How are they passed? | ✅/❌ |
| **Audit** | Are MCP actions logged? Can we trace what it accessed? | ✅/❌ |
| **Scope** | Is the MCP restricted to safe folders? (docs/, examples/, tests/) | ✅/❌ |
| **Approval** | Has security team reviewed this integration? | ✅/❌ |

### Current MCP Integrations

**Current state**: No MCP server is configured in this project — no `.mcp.json` file exists yet. "Layer 06" describes the review *process* to follow once one is requested, not an already-installed integration.

### Adding New MCP Servers

**Process**:
1. Request MCP integration (create issue in GitLab with MCP details)
2. Security review (review checklist above)
3. Scope definition (which paths can MCP access?)
4. Approval (security + architecture team sign-off)
5. Add the server to a project-root **`.mcp.json`** file (not `.claude/settings.json` — `mcpServers` is not a recognized `settings.json` key); scope its tool access via `permissions.allow`/`ask`/`deny` in `settings.json` if needed
6. Document in [docs/guides/mcp-integrations.md](../../docs/guides/) (if added)

---

## Layer 07: Audit & Traceability — Sessions, PRs, Settings Versioned

**Definition**: All decisions, settings, and changes are versioned and traceable.

### Session Tracking

**What is tracked**:
- Claude Code session start/end times
- Commands executed (tools, files accessed)
- Changes made (file edits, creations, deletions)
- Decisions (approval/rejection of changes)
- Errors and warnings

**Where stored**:
- VS Code: Local in `.vscode/extensions/ms-vscode.copilot/`
- Server (if enabled): Anthropic's secure logging

**Access**:
```bash
# View current session
vs code → Extensions → Copilot → Sessions

# Export session for audit
# (Manual from VS Code UI)
```

### MR/PR Traceability

**Required for every MR**:
- ✅ Commit messages (atomic, descriptive)
- ✅ MR description (template in [CONTRIBUTING.md](../../CONTRIBUTING.md))
- ✅ Approval chain (code review → security → merge)
- ✅ CI/CD log (lint, test, coverage artifacts)

**Example MR audit trail**:
```
MR #42: Add BM25Retriever adapter
├── Branch: feature/bm25-retriever
├── Commits:
│   ├── c3a2f1e: Add BM25Retriever implementation + tests
│   ├── b9e7f2d: Add conformance test + registration
│   └── a1d8c9f: Update CHANGELOG.md
├── CI/CD:
│   ├── lint: ✅ ruff check passed
│   ├── test:unit: ✅ 15 tests passed
│   ├── test:contract: ✅ 3 conformance tests passed
│   └── coverage: ✅ 92% (new code 100%)
├── Reviews:
│   ├── @architecture: ✅ Approved
│   ├── @security: ✅ Approved
│   └── @test: ✅ Approved
└── Merged: 2026-06-19 14:30 UTC
```

### Configuration Versioning

**Files tracked for changes**:

| File | Purpose | Review Required |
|------|---------|-----------------|
| `.claude/.instructions.md` | Architecture rules | ✅ Breaking changes |
| `.claude/.prompt.md` | Response style | ✅ Tone/format changes |
| `.claude/settings.json` | Permissions, hooks | ✅ Permission changes |
| `.claude/rules/*.md` | Domain-specific rules | ✅ All changes |
| `CONTRIBUTING.md` | Development workflow | ✅ Process changes |
| `.gitlab-ci.yml` | CI/CD pipeline | ✅ Test scopes, tools |
| `pyproject.toml` | Dependencies, versions | ✅ Dependency adds |
| `docs/adr/*.md` | Architectural decisions | ✅ All decisions |

### Traceability Example

**Scenario**: Adding new ruff rule to CI/CD

```
1. Issue created: "Add ruff rule for type checking"
   Reporter: @dev
   Description: Add B (flake8-bugbear) rule
   
2. Branch created: feature/add-bugbear-rule
   
3. Changes made:
   - .gitlab-ci.yml: Updated ruff --select to include B
   - CLAUDE.md block 05: Document B rule requirement
   - docs/guides/validation.md: Update ruff section
   
4. Commit: "feat: Add flake8-bugbear (B) to ruff linting"
   
5. MR #43 created
   - CI/CD runs (all stages pass)
   - Reviews: ✅ @architecture, ✅ @security
   
6. Merged to main
   
7. Audit trail:
   - Git history: commit c5a3b2e visible in `git log`
   - CI artifacts: All logs stored in GitLab
   - Settings versioned: .gitlab-ci.yml v1.5 tagged
```

### Audit Retention Policy

**Requirements**:
- ✅ Git history: Indefinite (immutable via remote)
- ✅ CI/CD logs: 90 days (GitLab free tier default)
- ✅ Session logs: 30 days (VS Code local)
- ✅ MR approvals: Indefinite (GitLab immutable)
- ✅ Configuration changes: Indefinite (Git version history)

### Compliance Queries

**How to audit**:

```bash
# Who changed what, when?
git log --oneline --follow -- CLAUDE.md

# What was in this rule version at commit hash?
git show abc123:CLAUDE.md | head -50

# Which MRs touched orchestration/?
git log --grep="orchestration" --oneline

# All commits by user between dates
git log --author="@username" --since="2026-05-01" --until="2026-06-01" --oneline

# Who approved that MR? (GitLab CLI)
glab mr view 42 --web  # Opens approval chain
```

---

## Security Stack Summary

| Layer | Control | Tools | Status |
|-------|---------|-------|--------|
| **01** | Permissions | `.claude/settings.json` | ✅ Implemented |
| **02** | Hooks | PostToolUse (ruff) — `matcher: "Edit|Write"` lints full `src/+tests/` tree | ✅ Implemented |
| **03** | Policies | CLAUDE.md (9 blocks + local), CONTRIBUTING.md | ✅ Implemented |
| **04** | Segmentation | Folder boundaries + permission matrix | ✅ Implemented |
| **05** | Secrets | .env + .gitignore + code patterns | ✅ Implemented |
| **06** | MCP | Governance checklist + review process | ✅ Implemented |
| **07** | Audit | Git + MR + session tracking | ✅ Implemented |

---

## What Next?

**For developers**: Understand layers 1-7 when writing code. Use them as your security baseline.

**For security reviews**: Use this document as a checklist. Every change should satisfy at least 3 layers.

**For architecture**: Layer 6 (MCP) and Layer 7 (Audit) scale to V2+. Layer 5 (Secrets) extends with encryption key management in V4.

---

## References

- [CLAUDE.md](../../CLAUDE.md) — Project policies (blocks 01-09)
- [.claude/settings.json](../settings.json) — Permissions configuration
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Git workflow, MR process
- [docs/adr/0003-security-and-governance.md](../../docs/adr/0003-security-and-governance.md) — Governance decisions
- [.gitignore](../../.gitignore) — Secret and artifact patterns
