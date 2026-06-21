# Claude Code Complete Configuration Guide

**For**: All developers  
**Purpose**: Understand how Claude Code is configured and integrated into the Modular RAG Framework  
**Updated**: June 20, 2026  
**Status**: Production Ready ✅

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Why This Matters](#why-this-matters)
3. [The 3 Founding Principles](#the-3-founding-principles)
4. [7-Layer Security Strategy](#7-layer-security-strategy)
5. [4 Platform Mechanisms](#4-platform-mechanisms)
6. [Configuration Files Reference](#configuration-files-reference)
   - **[→ Complete Development Guide (2,500 lines)](./claude-code-complete-development-guide.md)** — End-to-end workflow ⭐
   - **[→ Settings Reference (1,500 lines)](./claude-code-settings-reference.md)** — All 100+ settings
   - **[→ MCP Setup (1,000 lines)](./claude-code-mcp-setup.md)** — Model Context Protocol
   - **[→ Plugins & Marketplaces (1,000 lines)](./claude-code-plugins-marketplaces.md)** — Team plugins
   - **[→ Advanced Configuration (800 lines)](./claude-code-advanced-config.md)** — Subagents, skills, hooks
   - **[→ Enterprise Deployment (600 lines)](./claude-code-enterprise-deployment.md)** — MDM, Group Policy
7. [The 6-Step Workflow](#the-6-step-workflow)
8. [Available Commands](#available-commands)
9. [Success Metrics & Tracking](#success-metrics--tracking)
10. [Advanced: Sub-Agents](#advanced-sub-agents)
11. [Quick Reference](#quick-reference)
12. [Getting Help](#getting-help)

---

## Executive Summary

Claude Code has been **industrialized** on this project with comprehensive governance, standardization, and measurement. This isn't a tool rollout—it's a structured engineering asset.

**What you get**:
- ✅ Clear rules everyone follows (CLAUDE.md 9 blocks)
- ✅ Automated validation (scripts/check.sh)
- ✅ Consistent commands across team (/quick-check, /full-check, etc.)
- ✅ Security by design (7 layers of defense)
- ✅ Measured adoption (KPIs tracked weekly)
- ✅ Team onboarding (1-day productivity path)

**Key metrics**:
- Target adoption: 80% by day 90
- Target code quality: Same or better than human
- Target validation time: <5 min
- Target architecture violations: 0

---

## Why This Matters

### The Problem
- Individual teams use Claude Code differently
- No consistent standards across repos
- Hard to review AI-assisted code
- Difficult to measure impact
- Knowledge scattered across teams

### The Solution
This guide defines:
1. **How** Claude Code works on this project (standards)
2. **What** Claude can and cannot do (rules)
3. **Why** we do it this way (principles)
4. **How to measure** success (metrics)

### The Outcome
- **Reproducible**: Any developer follows the same process
- **Governed**: Clear boundaries prevent misuse
- **Measured**: Progress tracked against KPIs
- **Scalable**: Process works for 1 team or 100

---

## The 3 Founding Principles

Your configuration is built on **three non-negotiable principles**:

### 1. 🔄 PROGRESSIVE

**Definition**: Adopt Claude Code gradually through phases, never skip steps.

**Implementation**:
- V1 (Core RAG) ✅ — End-to-end working
- V2 (Agentic) ⏳ — Deferred, rules documented
- V3 (Graph Memory) ⏳ — Deferred
- V4 (Governance) ⏳ — Deferred
- V5 (Multimodal) ⏳ — Deferred

**What this means for you**:
- Don't implement V2+ features yet (even if possible)
- Follow the version progression in [CLAUDE.md block 09](../../CLAUDE.md#09--known-stubs--v2-scope)
- Focus on V1: ingestion, retrieval, generation, eval, security

**Example**: Want to add an LLM adapter? → Check if it's V1 or V2+ scope → If V2+, defer to next phase

---

### 2. 📐 STANDARDIZED

**Definition**: Common language, files, and workflows across all repos and team members.

**Implementation**:
- **9-block CLAUDE.md** — Standard project policy template
- **3 domain CLAUDE.md files** — security/, orchestration/, contracts/
- **Standard commands** — /quick-check, /full-check, /add-component, etc.
- **Standard validation** — scripts/check.sh (quick/full/integration/e2e/all)
- **Standard git workflow** — CONTRIBUTING.md (branch naming, commit format, MR process)
- **Standard permissions** — 3-tier model in settings.json (denylist/noAsk/autoAccept/restricted)

**What this means for you**:
- Everyone uses the same validation commands
- Everyone follows the same git workflow
- Everyone reads the same CLAUDE.md
- New team members onboard in <1 day

**Example**: Adding a new chunker? → Follow CONTRIBUTING.md → Use /add-component → Validate with /full-check

---

### 3. 📊 MEASURED

**Definition**: Metrics from day 1, tracked continuously to ensure quality and adoption.

**Implementation**:
- **7 KPIs** tracked weekly (completion rate, bug rate, adoption, validation time, coverage, review time, violations)
- **90-day success criteria** with targets for days 30/60/90
- **Weekly standup template** for reporting
- **Monthly dashboard** for leadership
- **Red flags** defined for escalation

**What this means for you**:
- Progress is visible and trackable
- Success/failure is measurable, not opinion-based
- Team adjusts based on data

**Example**: By day 90, team adoption should be 80% + bug rate ≤ baseline + test coverage ≥92%

---

## 7-Layer Security Strategy

Your security is protected by **7 independent layers**, each with a different control:

### Layer 01: Permissions (First Line of Control)

**What it does**: Globally defines what is possible. Granular per-path.

**3-Tier Model**:
```
BLOCKED BY DEFAULT (Denylist — always no)
    ↓
Tier 1: DONTASK (tests/, examples/, docs/ — zero friction)
    ↓
Tier 2: ACCEPTEDITS (ingestion/, retrieval/, generation/, eval/, memory/ — auto-accept)
    ↓
Tier 3: ASK_BEFORE_EDIT (contracts/, orchestration/, security/, adapters/embeddings, adapters/vectorstores)
```

**Configuration**: `.claude/settings.json` (permissions section)

**Examples**:
- ❌ BLOCKED: `.env`, `manifests/production/`, `.claude/rules/`, `adapters/llms/`
- ✅ DONTASK: `tests/`, `examples/`, `docs/`
- ✅ ACCEPTEDITS: New chunkers, retrievers, generators
- ✅ ASK_BEFORE_EDIT: Protocol changes, registry changes, security rules

**Why it matters**: Prevents accidental breaking changes while encouraging component development

---

### Layer 02: Hooks (Contextual Control at Runtime)

**What it does**: Automatic validation after file writes.

**PostToolUse Hooks** (implemented):
- After every file edit → `ruff check src/modular_rag/ tests/ --select E,F,I`
- Catches: syntax errors, undefined names, import order violations
- Runs automatically (no manual intervention)

**FutureHooks** (V2+ reserved):
- Cross-domain import detection
- Protocol conformance checking
- Lazy import validation

**Configuration**: `.claude/settings.json` (hooks section)

**Why it matters**: Fail-fast — errors caught immediately, not in CI/CD

---

### Layer 03: CLAUDE.md & Project Policies

**What it does**: Expected behaviors, sensitive areas, business rules.

**Files**:
- [CLAUDE.md](../../CLAUDE.md) — 9-block project policy
- [src/modular_rag/security/CLAUDE.md](../../src/modular_rag/security/CLAUDE.md) — Safety vs Security distinction
- [src/modular_rag/orchestration/CLAUDE.md](../../src/modular_rag/orchestration/CLAUDE.md) — Registry patterns
- [src/modular_rag/contracts/CLAUDE.md](../../src/modular_rag/contracts/CLAUDE.md) — Protocol-first approach
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Git workflow

**Why it matters**: Human-readable rules that are the "why" behind permissions

---

### Layer 04: Folder Segmentation (Strict Write Boundaries)

**What it does**: Structure enforces permission model through folder layout.

**Segmentation**:
```
src/modular_rag/
├── cli/, api/, app/              ← Restricted (top-level entry points)
├── orchestration/                ← Ask-before-edit (central wiring)
├── contracts/                    ← Ask-before-edit (Protocol definitions)
├── core/                         ← Ask-before-edit (foundation layer)
├── security/                     ← Ask-before-edit (sensitive)
├── ingestion/                    ← Auto-accept (safe domain)
├── retrieval/                    ← Auto-accept (safe domain)
├── generation/                   ← Auto-accept (safe domain)
├── eval/                         ← Auto-accept (safe domain)
├── memory/                       ← Auto-accept (safe domain)
├── adapters/
│   ├── embeddings/              ← Ask-before-edit (Protocol implementations)
│   ├── vectorstores/            ← Ask-before-edit (Protocol implementations)
│   ├── llms/                    ← BLOCKED (V2+ scope)
│   ├── auth/                    ← BLOCKED (V4+ scope)
│   ├── graphstores/             ← BLOCKED (V3+ scope)
│   └── search/                  ← BLOCKED (V2-V3 scope)
```

**Why it matters**: Structure prevents cross-module contamination; V2+ reserved namespaces protected

---

### Layer 05: Secret Management (No Hardcoding, Full Block)

**What it does**: Secrets never hardcoded, committed, or exposed.

**Implementation**:
- `.env` pattern blocked: `.env`, `.env.local`, `.env.*.local`
- `.env.example` exists as template for developers
- Detailed `.gitignore` documentation
- Code patterns shown (use `os.getenv()`, never hardcode)
- PII redaction in security module

**Why it matters**: Prevents accidental credential exposure

---

### Layer 06: MCP Governance (Security Review of External Integration)

**What it does**: Every external MCP integration reviewed before deployment.

**Process**:
1. Request MCP (GitLab issue)
2. Security review (7-point checklist)
3. Scope definition (allowPaths + denyPaths)
4. Add to settings.json
5. Document in [docs/guides/mcp-integrations.md](../../docs/guides/mcp-integrations.md)

**Review Checklist**:
- ✅ Source verified (trusted vendor/OSS)
- ✅ Capabilities scoped (read-only vs write)
- ✅ Secrets safe (env vars, not hardcoded)
- ✅ Audit trail (MCP actions logged)
- ✅ Scope restricted (safe folders only)
- ✅ Secrets storage (VS Code secrets)
- ✅ Approval (security team sign-off)

**Why it matters**: External integrations are security boundaries; reviewing them prevents breaches

---

### Layer 07: Audit & Traceability (Sessions, PRs, Settings Versioned)

**What it does**: All decisions, settings, changes versioned and traceable.

**Tracked**:
- Git history (commits, MRs)
- MR/PR approvals (approval chain)
- Configuration versions (.claude/.instructions.md, settings.json, etc.)
- Session logs (Claude Code usage)
- CI/CD artifacts (lint, test, coverage)

**Retention Policy**:
- Git history: Indefinite
- CI/CD logs: 90 days
- Session logs: 30 days
- MR approvals: Indefinite

**Why it matters**: Complete audit trail for compliance and debugging

---

## 4 Platform Mechanisms

### Mechanism 1: 🎣 Hooks

**What it does**: Triggers automatic actions at specific lifecycle points.

**PostToolUse Hooks** (active):
```json
{
  "matcher": "Edit|Write",
  "filePattern": "src/modular_rag/**/*.py|tests/**/*.py",
  "command": "ruff check src/modular_rag/ tests/ --select E,F,I --quiet"
}
```

**Trigger**: After every file write  
**Action**: Lint with ruff  
**Result**: Immediate feedback (pass/fail)

**FutureHooks** (V2+ reserved):
- Cross-domain import detection
- Conformance validation
- Lazy import checking

**Configuration**: `.claude/settings.json` → hooks section

---

### Mechanism 2: 🧠 Skills

**What it does**: Formalized reusable workflows, callable by Claude or humans.

**7 Domain-Specific Rules** (act as skills):
1. [orchestration.md](../../.claude/rules/orchestration.md) — Registry patterns, engine flow
2. [adapters.md](../../.claude/rules/adapters.md) — External bindings, lazy imports, Protocol implementation
3. [agents.md](../../.claude/rules/agents.md) — Agent interfaces, state passing, TraceStep
4. [agentic_workflows.md](../../.claude/rules/agentic_workflows.md) — V2+ coordination patterns
5. [contracts.md](../../.claude/rules/contracts.md) — Protocol-first development
6. [security.md](../../.claude/rules/security.md) — Safety vs Security distinction
7. [tests.md](../../.claude/rules/tests.md) — Testing conventions

**Plus meta-rules**:
- [security-layers.md](../../.claude/rules/security-layers.md) — 7-layer defense system
- [.instructions.md](../../.claude/.instructions.md) — Global architecture rules
- [.prompt.md](../../.claude/.prompt.md) — Response style guide

**Configuration**: Automatic discovery via `.claude/rules/` + `applyTo` patterns

**Example**: When editing `src/modular_rag/adapters/embeddings/huggingface.py`, automatically loads `adapters.md` rules

---

### Mechanism 3: ⚡ Custom Commands

**What it does**: Team-wide slash commands for common workflows.

**5 Available Commands** (in `.claude/AGENTS.md`):

| Command | Purpose | Time | Use When |
|---------|---------|------|----------|
| `/quick-check` | Syntax + imports | 30s | After code edits |
| `/full-check` | Unit + contract tests | 2-5m | Before MR |
| `/validate-security` | Security layer compliance | 5-10m | Security-sensitive changes |
| `/add-component` | Scaffolding template | 10m | New adapter/component |
| `/release` | Pre-release validation | 10m | Before tagging release |

**Example**:
```
You:  /quick-check
Claude: Runs ./scripts/check.sh quick and reports results
```

**Configuration**: `.claude/AGENTS.md` — describes each command

---

### Mechanism 4: 🔄 CI/CD Integration

**What it does**: Local validation matches CI/CD exactly (no "passes locally, fails in CI" surprises).

**Local Validation** (`scripts/check.sh`):
```bash
quick        # Syntax + imports (ruff E,F,I)
full         # Unit + contract tests
integration  # Add integration tests (needs Qdrant)
e2e          # Full pipeline (needs LLM API)
all          # All checks (10 min)
```

**CI/CD** (`.gitlab-ci.yml`):
```yaml
lint:       # ruff check (E,F,I,N,W,UP,B,C4) + mypy
test:unit:  # pytest tests/unit/
test:contract: # pytest tests/contract/
coverage:   # pytest with coverage report
```

**Key insight**: Local `./scripts/check.sh full` ≈ CI/CD pipeline. Developers can validate before pushing.

**Configuration**: `.gitlab-ci.yml` + `scripts/check.sh`

---

## Configuration Files Reference

### Core Configuration Files

| File | Purpose | Size | Edited By |
|------|---------|------|-----------|
| **CLAUDE.md** | Project policy (9 blocks) | 350 lines | Architecture team |
| **.claude/.instructions.md** | Global rules for Claude | 800 lines | Architecture team |
| **.claude/.prompt.md** | Response style guide | 700 lines | Architecture team |
| **.claude/settings.json** | Permissions + hooks | 200 lines | Architecture team |
| **.claude/AGENTS.md** | Custom commands | 350 lines | Architecture team |
| **.claude/rules/*.md** | Domain-specific rules | 3,500 lines | Domain owners |
| **.env.example** | Template environment vars | 20 lines | Any developer |
| **.gitignore** | Git exclusions (documented) | 150 lines | Any developer |
| **CONTRIBUTING.md** | Git workflow + MR process | 300 lines | Architecture team |
| **scripts/check.sh** | Validation script | 250 lines | Architecture team |
| **.gitlab-ci.yml** | CI/CD pipeline | 60 lines | DevOps/Architecture |

### Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| [docs/guides/onboarding-claude-code.md](../../docs/guides/onboarding-claude-code.md) | Team onboarding (1-day productivity) | New developers |
| [docs/guides/validation.md](../../docs/guides/validation.md) | Command reference | All developers |
| [docs/guides/validation-protocol.md](../../docs/guides/validation-protocol.md) | Formal protocol definition | All developers |
| [docs/guides/adoption-metrics.md](../../docs/guides/adoption-metrics.md) | Success metrics + dashboards | Tech leads |
| [docs/guides/mcp-integrations.md](../../docs/guides/mcp-integrations.md) | External tool integration process | Architecture team |
| [docs/guides/subagents-parallelization.md](../../docs/guides/subagents-parallelization.md) | Advanced sub-agent patterns | Advanced users |
| [docs/guides/working-with-agents.md](../../docs/guides/working-with-agents.md) | V2+ agent patterns (reference) | Future implementation |
| [docs/adr/](../../docs/adr/) | Architectural decision records | Decision context |
| [docs/architecture/](../../docs/architecture/) | Technical architecture | All developers |

### Development Workflow Guide (The Complete Picture) 🆕

**Master the end-to-end development process:**

| Guide | Size | Coverage | Audience |
|-------|------|----------|----------|
| **[claude-code-complete-development-guide.md](./claude-code-complete-development-guide.md) 🆕** | 2,500 lines | **COMPLETE WORKFLOW** from problem to commit | All developers |
| ↳ 5-minute quick start | 5 min | Prerequisites, rules, commands | All |
| ↳ 5-phase workflow | 30 min | EXPLORE → DESIGN → IMPLEMENT → VALIDATE → REVIEW | All |
| ↳ Architecture rules | 20 min | Hexagonal layering, imports, wiring, observability | All |
| ↳ Pattern library | 30 min | Retrievers, guards, generators, metrics | Implementers |
| ↳ Real-world examples | 40 min | BM25 retriever, PII detection with full code | Implementers |
| ↳ Validation & testing | 15 min | Test scopes, checklist | All |
| ↳ Debugging | 20 min | Common errors, root causes, fixes | All |
| ↳ Anti-patterns | 15 min | What NOT to do, with corrections | All |

**→ START HERE if you're building a feature or joining the team!**

### Advanced Configuration Guides (Reference)

**Comprehensive reference for Claude Code configuration:**

| Guide | Size | Coverage | Audience |
|-------|------|----------|----------|
| [claude-code-settings-reference.md](./claude-code-settings-reference.md) | 1,500 lines | All 100+ settings, scopes, precedence | All developers |
| [claude-code-mcp-setup.md](./claude-code-mcp-setup.md) | 1,000 lines | MCP configuration, built-in servers, custom servers | Integration leads |
| [claude-code-plugins-marketplaces.md](./claude-code-plugins-marketplaces.md) | 1,000 lines | Plugin system, marketplace setup, governance | DevOps/Architecture |
| [claude-code-advanced-config.md](./claude-code-advanced-config.md) | 800 lines | Subagents, skills, path-scoped rules, hooks | Advanced users |
| [claude-code-enterprise-deployment.md](./claude-code-enterprise-deployment.md) | 600 lines | Managed settings, MDM, Group Policy, deployment | IT/DevOps teams |

**Quick Navigation by Need:**

- **"I'm building a feature"** → [claude-code-complete-development-guide.md](./claude-code-complete-development-guide.md) ⭐
- **"I want to understand ALL settings"** → [claude-code-settings-reference.md](./claude-code-settings-reference.md)
- **"How do I integrate with GitHub/Slack?"** → [claude-code-mcp-setup.md](./claude-code-mcp-setup.md)
- **"How do I set up team plugins?"** → [claude-code-plugins-marketplaces.md](./claude-code-plugins-marketplaces.md)
- **"I need advanced features like subagents/hooks"** → [claude-code-advanced-config.md](./claude-code-advanced-config.md)
- **"I'm deploying Claude Code across an organization"** → [claude-code-enterprise-deployment.md](./claude-code-enterprise-deployment.md)

---

## The 6-Step Workflow

**Universal workflow** that applies regardless of task type (feature, bugfix, refactor).

### Step 1️⃣: EXPLORE (Understand Before Acting)

**Goal**: Understand the problem deeply before coding.

**Actions**:
- Read relevant documentation (CLAUDE.md, architecture docs, ADRs)
- Ask Claude to explore existing code patterns
- Identify constraints and dependencies
- Clarify requirements with team

**Time**: 5-15 min

**Example**: "I need to add a BM25 retriever"
```
✓ Read CLAUDE.md blocks 1-5 (project rules)
✓ Explore: How do retrievers work? (read VectorRetriever)
✓ Explore: Where are retrievers registered? (read _default_factories.py)
✓ Clarify: Should BM25 be standalone or hybrid? (ask maintainer)
```

---

### Step 2️⃣: PLAN (Break into Observable Steps)

**Goal**: Create a detailed, step-by-step plan.

**Actions**:
- Break task into 3-5 concrete steps
- Estimate effort for each step
- Identify risk areas
- Get human approval before proceeding

**Time**: 5-10 min

**Example**: BM25 retriever plan
```
Step 1: Implement BM25Retriever in src/modular_rag/retrieval/bm25_retriever.py (45 min)
Step 2: Write unit tests (30 min)
Step 3: Register in _default_factories.py (5 min)
Step 4: Add contract conformance test (15 min)
Step 5: Add to example manifest (5 min)

Total: ~100 min
Risk: BM25 algorithm complexity
```

---

### Step 3️⃣: VALIDATE (Get Approval Before Implementation)

**Goal**: Validate plan with human before starting coding.

**Actions**:
- Share plan with team
- Discuss approach (will it work?)
- Get sign-off from architecture owner
- Address any concerns

**Time**: 5-10 min (async, usually via comment/chat)

**Example**:
```
You:     Here's my plan for BM25Retriever...
Team:    ✅ Looks good. One question: how will you handle ranking?
You:     Via RRF with vector retriever (see step 1)
Team:    ✅ Approved. Proceed.
```

---

### Step 4️⃣: IMPLEMENT (Code in Increments, One Topic at a Time)

**Goal**: Execute the plan incrementally, validating after each step.

**Actions**:
- Implement one step at a time
- Test locally (./scripts/check.sh quick)
- Get feedback from Claude if stuck
- Commit after each logical piece

**Time**: Depends on task (typically 1-3 hours for adapter)

**Example**:
```bash
# Step 1: Implement BM25Retriever
# Claude: "Implement src/modular_rag/retrieval/bm25_retriever.py
#  - Implement VectorRetriever Protocol
#  - Use rank_bm25 library
#  - Follow existing patterns from FixedChunker"
./scripts/check.sh quick

# Step 2: Write tests
# Claude: "Add tests/unit/retrieval/test_bm25_retriever.py
#  - Follow test_vector_retriever.py pattern"
./scripts/check.sh full

# Step 3: Register
# Claude: "Add BM25Retriever to _default_factories.py
#  - Name: 'bm25-retriever'"
./scripts/check.sh quick

# Step 4: Contract test
# (Add conformance test)
./scripts/check.sh full

# Step 5: Manifest
# (Update example YAML)
./scripts/check.sh quick
```

---

### Step 5️⃣: VERIFY (Lint, Test, Typecheck)

**Goal**: Ensure code quality before review.

**Actions**:
- Run full validation: `./scripts/check.sh full`
- All tests pass ✅
- No style violations ✅
- Coverage adequate ✅
- No architecture violations ✅

**Time**: 2-5 min

**Example**:
```bash
./scripts/check.sh full

✓ Quick checks passed (0.8s)
✓ Unit tests: 42 passed (2.1s)
✓ Contract tests: 8 passed (1.3s)
✓ Coverage: 92% (3.5s)
---
✓ All checks passed (7.7s)
```

---

### Step 6️⃣: DELIVER (Readable Commit or PR)

**Goal**: Create clear commit/MR that others can understand and review.

**Actions**:
- Create feature branch (feature/xyz)
- Atomic commits with clear messages (conventional format)
- Push to GitLab
- Create MR with template filled
- Request review

**Time**: 10-15 min

**Example**:
```bash
git checkout -b feature/bm25-retriever
git add -A
git commit -m "feat: Add BM25Retriever with RRF fusion support

Implements BM25-based text retrieval as standalone adapter.

Adds:
- BM25Retriever in src/modular_rag/retrieval/bm25_retriever.py
- Unit tests in tests/unit/retrieval/test_bm25_retriever.py
- Contract conformance test
- Registration in orchestration/_default_factories.py

Protocol: Implements VectorRetriever (retrieve, name, clear_cache)
Tests: 5 unit tests covering edge cases
Coverage: 100% (new code)

Fixes #42
"

git push origin feature/bm25-retriever

# Create MR on GitLab with template
```

---

## Available Commands

### Command Taxonomy

**Daily Commands** (use frequently):
- `/quick-check` — After code edits
- `/full-check` — Before MR
- `/validate-security` — For security-sensitive code

**Development Commands** (use when starting new work):
- `/add-component` — Scaffolding template for new adapter
- `/release` — Pre-release validation

### `/quick-check` — Fast Feedback Loop

**What it does**: Syntax + import validation (< 30 seconds)

**Equivalent**: `./scripts/check.sh quick`

**Checks**:
- ✅ Python syntax (ruff E: errors)
- ✅ Undefined names (ruff F: flakes)
- ✅ Import order (ruff I: isort)

**When to use**: After every code change, before committing

**Output**:
```
✓ Checking syntax and imports...
✓ All checks passed (0.8s)
```

**On failure**:
```
✗ Error in src/modular_rag/ingestion/chunker.py:42
  - undefined name 'Document' (did you import from contracts?)
  
Fix: Add import from modular_rag.core.models import Document
```

---

### `/full-check` — Comprehensive Validation

**What it does**: All unit + contract tests + coverage (2-5 minutes)

**Equivalent**: `./scripts/check.sh full`

**Checks**:
- ✅ Quick checks (syntax, imports)
- ✅ Unit tests (tests/unit/)
- ✅ Contract conformance tests (tests/contract/)
- ✅ Code coverage

**When to use**: Before pushing MR

**Output**:
```
✓ Quick checks passed (0.8s)
✓ Unit tests: 42 passed (2.1s)
✓ Contract tests: 8 passed (1.3s)
✓ Coverage: 92% (3.5s)
---
✓ All checks passed (7.7s)
```

---

### `/validate-security` — Security Layer Compliance

**What it does**: Verify adherence to security rules (5-10 minutes)

**Checks**:
- ✅ No hardcoded secrets (.env patterns)
- ✅ No cross-domain imports (retrieval ↔ generation)
- ✅ No direct component wiring (must use registry)
- ✅ Lazy imports on heavy dependencies
- ✅ PII patterns in security module correct

**When to use**: Before security-sensitive changes

**Output**:
```
✓ Security layer validation

Secrets check:
  ✓ No hardcoded API keys
  ✓ .env files gitignored
  
Cross-domain imports:
  ✓ ingestion/ has no generation imports
  ✓ retrieval/ has no memory imports
  
Adapter isolation:
  ✓ adapters/embeddings/ only imports core + contracts
  
Lazy imports:
  ✓ openai imported inside methods (3 locations)
  ✓ qdrant_client imported inside methods (2 locations)
  
---
✓ All security checks passed
```

---

### `/add-component` — Scaffolding Template

**What it does**: Create new component with full structure (10 min)

**Equivalent**: Manual scaffolding with templates

**Steps**:
1. Choose component type (chunker, retriever, generator, metric, embedder, vectorstore)
2. Name the component
3. Get scaffolded:
   - Implementation file with stubs
   - Unit test file with patterns
   - Contract conformance test
   - Registration hints

**Example**:
```
You: /add-component
     Type: Retriever
     Name: bm25_retriever
     Desc: "BM25-based lexical retrieval"

Claude creates:
  ✓ src/modular_rag/retrieval/bm25_retriever.py
  ✓ tests/unit/retrieval/test_bm25_retriever.py
  ✓ tests/contract/test_bm25_retriever_conformance.py (stub)
  ✓ Hints for registration in _default_factories.py
```

---

### `/release` — Pre-Release Validation

**What it does**: All checks including integration + e2e (10 minutes)

**Equivalent**: `./scripts/check.sh all`

**Checks**:
- ✅ Quick + full checks
- ✅ Integration tests (requires Qdrant)
- ✅ E2E tests (requires LLM API)
- ✅ Documentation builds
- ✅ CHANGELOG.md updated
- ✅ Version bumped in pyproject.toml
- ✅ ADR written (if structural change)

**When to use**: Before tagging a release

**Output**:
```
✓ Release validation

Pre-checks:
  ✓ Branch is main
  ✓ Working directory clean
  ✓ Latest from origin/main
  
Full validation:
  ✓ Quick checks passed
  ✓ Unit tests: 42 passed
  ✓ Contract tests: 8 passed
  ✓ Integration tests: 5 passed [Qdrant required]
  ✓ E2E tests: 3 passed [LLM API required]
  ✓ Coverage: 92%
  ✓ Docs build: OK
  ✓ CHANGELOG.md updated: YES
  ✓ Version bumped: YES (1.0.5)
  
---
✓ Ready for release v1.0.5
```

---

## Success Metrics & Tracking

### 7 Key Performance Indicators

#### 1. Task Completion Rate
**Definition**: % of Claude-assisted tasks that complete successfully

**Target**: 85%+ by day 90

**How to track**:
```
Success = (Completed tasks) / (Total tasks) × 100%

Week 1: 2 of 3 tasks completed = 67% ⚠️
Week 2: 4 of 5 tasks completed = 80% 🟡
Week 3: 8 of 9 tasks completed = 89% ✅
```

---

#### 2. Bug Introduction Rate
**Definition**: % of bugs from Claude-assisted code vs human baseline

**Target**: Claude rate ≤ human rate (ideally 20% better)

**How to track**:
```
Claude bug rate = (Claude bugs) / (Claude lines) per 1000 lines
Human bug rate = (Human bugs) / (Human lines) per 1000 lines

Example:
Claude: 5,000 lines, 1 bug → 0.2 bugs/1k ✅
Human: 4,000 lines, 2 bugs → 0.5 bugs/1k ✅
Result: Claude is 60% better
```

---

#### 3. Team Adoption Rate
**Definition**: % of team actively using Claude Code

**Target**: 30% day 30 → 50% day 60 → 80% day 90

**How to track**:
```
Adoption = (Active users in last 30 days) / (Total developers) × 100%

Day 15: 2/10 = 20% 🟡
Day 30: 3/10 = 30% ✅
Day 60: 5/10 = 50% ✅
Day 90: 8/10 = 80% ✅
```

---

#### 4. Validation Performance
**Definition**: Time to run full validation suite

**Target**: <5 minutes consistently

**How to track**:
```
./scripts/check.sh full
Runtime: 3.2 min ✅

Trend over time:
Week 1: 3.5 min
Week 2: 3.2 min ✓
Week 3: 3.0 min ✓
Week 4: 3.1 min → Alert: why slower?
```

---

#### 5. Test Coverage
**Definition**: % of source code covered by tests

**Target**: ≥92% (maintain or improve)

**How to track**:
```
pytest --cov=src/modular_rag --cov-report=term-missing
Coverage: 92% ✅

Trend:
Week 1: 89% 🟡 → Increase
Week 2: 90% 🟡 → Increase
Week 3: 91% 🟡 → Increase
Week 4: 92% ✅ → Maintain
```

---

#### 6. Code Review Time
**Definition**: Average time from MR creation to approval

**Target**: -20% vs baseline (reduce from ~6h to ~5h)

**How to track**:
```
Track MR times in GitLab:
- MR 1: Created Jun 20 10am, Approved Jun 20 4pm = 6 hours
- MR 2: Created Jun 21 9am, Approved Jun 21 2pm = 5 hours
- MR 3: Created Jun 22 10am, Approved Jun 22 3:30pm = 5.5 hours

Average: 5.5 hours ✅ (vs 6h baseline)
Improvement: 8.3% (target: 20%)
```

---

#### 7. Architecture Violations
**Definition**: # of errors caught (cross-domain imports, direct wiring, etc.)

**Target**: 0 (protected by hooks + review)

**How to track**:
```
Weekly violations:
Week 1: 2 (ingestion importing from generation, direct adapter instantiation)
       → Fixed via code review
Week 2: 1 (lazy import violation)
       → Fixed before CI/CD
Week 3: 0 ✅
Week 4: 0 ✅
Goal: Maintain 0
```

---

### 90-Day Success Criteria

**By Day 30** (Foundation):
- [ ] 100% of team trained (read CLAUDE.md + onboarding)
- [ ] Task completion rate ≥70%
- [ ] 0 bugs from Claude code
- [ ] Test coverage maintained ≥90%
- [ ] No architecture violations

**By Day 60** (Standardization):
- [ ] Team adoption ≥50%
- [ ] Validation time <5 min
- [ ] CI/CD test pass rate ≥95%
- [ ] Code review time -10% vs baseline
- [ ] Architecture violations: 0

**By Day 90** (Maturity):
- [ ] Team adoption ≥80%
- [ ] Task completion rate ≥85%
- [ ] Bug rate (Claude) ≤ bug rate (human)
- [ ] Team velocity +15%
- [ ] Test coverage ≥92%
- [ ] Onboarding time <2 days

---

### Weekly Standup Template

```markdown
## Claude Code Adoption — Week X

**Period**: [Start] → [End]

### Metrics Summary

| Metric | Week X | Target | Status |
|--------|--------|--------|--------|
| Completion rate | 80% | 85%+ | 🟡 |
| Bug rate | 0.3/1k | ≤baseline | ✅ |
| Team adoption | 45% | 80% D90 | 🟡 |
| Validation time | 3.1m | <5m | ✅ |
| Test coverage | 91% | ≥92% | 🟡 |
| Review time | 5.5h | -20% | 🟡 |
| Violations | 0 | 0 | ✅ |

### Highlights

- ✅ [Success 1]: [Description]
- ✅ [Success 2]: [Description]
- 🟡 [In Progress]: [Description]

### Blockers

- [Blocker 1]: [Description] → [Plan to resolve]

**Prepared by**: [Name] | **Date**: [Date]
```

---

## Advanced: Specialized Sub-Agents (V1 Production-Ready)

### What Are Specialized Sub-Agents?

**8 domain-specialized sub-agents** focused on RAG framework development:

1. **@retrieval-specialist** — Vector search, BM25, fusion, ranking algorithms
2. **@ingestion-specialist** — Document processing, chunking, preprocessing  
3. **@generation-specialist** — LLM selection, prompt engineering, multi-model
4. **@security-specialist** — Guards, PII redaction, compliance (Safety ≠ Security)
5. **@architecture-reviewer** — Layering validation, imports, design patterns
6. **@test-specialist** — Test design, coverage, quality metrics
7. **@orchestration-specialist** — Registry patterns, manifest-driven wiring
8. **@observability-expert** — Tracing, metrics, performance analysis

### How to Use

**In chat**: Type directly
```
@retrieval-specialist I need a hybrid retriever combining vector + BM25.
What fusion algorithm should I use?
```

**In code**: Add comments  
```python
# @generation-specialist TODO: Reduce hallucination rate from 15% to <5%
```

### Subagent + Skill Mapping

Each subagent has a reusable **Skill** (workflow):

| Subagent | Skill | Time |
|----------|-------|------|
| @retrieval-specialist | `/design-retriever-fusion` | 2-3 hours |
| @ingestion-specialist | `/optimize-chunking` | 1.5-2 hours |
| @generation-specialist | `/add-generator` | 1.5-2 hours |
| @security-specialist | `/add-security-guard` | 1.5 hours |
| @architecture-reviewer | `/validate-architecture` | 10-15 min |
| @test-specialist | `/prepare-evaluation` | 1.5 hours |
| @orchestration-specialist | `/design-retriever-fusion` | 2-3 hours |
| @observability-expert | `/parallel-feature-analysis` | 30 min (first), 10 min (subsequent) |

### Parallelization

Run multiple subagents in **parallel** for faster analysis:

```python
# Analyze 3 domains simultaneously via /parallel-feature-analysis
await asyncio.gather(
    invoke_subagent("retrieval-specialist", task),
    invoke_subagent("generation-specialist", task),
    invoke_subagent("security-specialist", task)
)
# Result: 3 hours serial work → 1 hour parallel (3x speedup)
```

### Example: Hybrid Retriever Design

**Task**: Build HybridRetriever (vector + BM25 + reranking)

```
Step 1: @retrieval-specialist — Recommend fusion algorithm
  → "Use RRF (Reciprocal Rank Fusion) with weighted combination for optimal balance"

Step 2: /design-retriever-fusion skill
  → 6-step workflow: profiling → choose fusion → implement → test → rerank → register

Step 3: @architecture-reviewer — Validate protocol compliance
  → "HybridRetriever correctly implements VectorRetriever Protocol"

Step 4: @test-specialist — Design test coverage
  → "Unit: 3 tests (vector-only, bm25-only, fusion logic)
     Contract: 2 tests (Protocol conformance)
     Integration: 2 tests (with real Qdrant + index)"

Result: Production-ready HybridRetriever in ~2 hours
```

**See**: [.claude/AGENTS.md](../../.claude/AGENTS.md) — Full subagent reference  
**See**: [docs/guides/claude-code-parallelization-orchestration.md](./claude-code-parallelization-orchestration.md) — Parallelization patterns

---

## Quick Reference

### Commands Cheat Sheet

```bash
# Daily validation
./scripts/check.sh quick        # 30 sec → after edits
./scripts/check.sh full         # 3 min → before MR
./scripts/check.sh all          # 10 min → pre-release

# Claude commands (in chat)
/quick-check                    # Same as ./scripts/check.sh quick
/full-check                     # Same as ./scripts/check.sh full
/validate-security             # Security layer checks
/add-component                  # New adapter scaffolding
/release                        # Pre-release validation

# Git workflow
git checkout -b feature/xyz     # Branch naming
git add -A
git commit -m "feat: description"  # Conventional format
git push origin feature/xyz
# Create MR on GitLab
```

### File Locations Cheat Sheet

| Need | File | Line Count |
|------|------|-----------|
| Project rules | [CLAUDE.md](../../CLAUDE.md) | 350 |
| Architecture rules | [.claude/.instructions.md](../../.claude/.instructions.md) | 800 |
| Response style | [.claude/.prompt.md](../../.claude/.prompt.md) | 700 |
| Permissions | [.claude/settings.json](../../.claude/settings.json) | 200 |
| Commands | [.claude/AGENTS.md](../../.claude/AGENTS.md) | 350 |
| Domain rules | [.claude/rules/](../../.claude/rules/) | 3,500 |
| Git workflow | [CONTRIBUTING.md](../../CONTRIBUTING.md) | 300 |
| Onboarding | [docs/guides/onboarding-claude-code.md](../../docs/guides/onboarding-claude-code.md) | 1,200 |
| Validation | [docs/guides/validation.md](../../docs/guides/validation.md) | 600 |
| Metrics | [docs/guides/adoption-metrics.md](../../docs/guides/adoption-metrics.md) | 900 |
| Sub-Agents | [docs/guides/subagents-parallelization.md](../../docs/guides/subagents-parallelization.md) | 850 |
| MCP | [docs/guides/mcp-integrations.md](../../docs/guides/mcp-integrations.md) | 650 |

### Decision Tree

```
Q: I need to add a new component
A: Use /add-component or follow CONTRIBUTING.md

Q: My code is failing tests
A: Read error → Ask Claude → Read CLAUDE.md rules → Fix → /full-check

Q: Can I implement X?
A: Check CLAUDE.md block 09 (V1 vs V2+ scope)

Q: I don't understand a rule
A: Read relevant CLAUDE.md domain file + CONTRIBUTING.md

Q: How do I know if my change will break something?
A: Use sub-agents (Mapping agent)

Q: What's the success criteria?
A: See adoption-metrics.md (90-day targets)

Q: I'm stuck
A: Read "Getting Help" section below
```

---

## Getting Help

### I Made a Mistake

**Option 1**: Ask Claude to fix it
```
You: "My code is failing this test [error]. What went wrong?"
Claude: "The issue is X. To fix: Y."
You: Apply fix → /quick-check → test again
```

**Option 2**: Check CLAUDE.md rules
```
Error mentions "cross-domain import"?
→ Read CLAUDE.md block 02 (Architecture rules)
→ Understand why it's forbidden
→ Ask Claude: "How do I implement this without cross-domain imports?"
```

**Option 3**: Ask maintainer
```
In Slack or issue comment:
"I'm stuck on [problem]. Context: [details]. Help?"
```

---

### I Don't Understand a Rule

1. **Find the rule**: Search CLAUDE.md or .claude/rules/
2. **Read the context**: Each rule explains the "why"
3. **See examples**: Rules include ✅ good and ❌ bad examples
4. **Ask Claude**: "According to [file], [rule]. Can I do X?"
5. **Discuss with team**: If still unclear, raise in team sync

---

### I Want to Learn More

**Architecture**:
- [docs/architecture/overview.md](../../docs/architecture/overview.md)
- [docs/adr/](../../docs/adr/) (architectural decisions)

**Project**:
- [CLAUDE.md](../../CLAUDE.md) (all 9 blocks)
- [CONTRIBUTING.md](../../CONTRIBUTING.md) (git workflow)

**Claude Code**:
- [docs/guides/onboarding-claude-code.md](../../docs/guides/onboarding-claude-code.md) (first day)
- [docs/guides/validation.md](../../docs/guides/validation.md) (commands)
- [docs/guides/subagents-parallelization.md](../../docs/guides/subagents-parallelization.md) (advanced)

**External**:
- [Anthropic Claude Code docs](https://code.visualstudio.com/docs/copilot/overview)
- [GitHub Copilot Chat](https://docs.github.com/en/copilot/using-github-copilot/getting-started-with-github-copilot)

---

### I Found a Bug or Have an Idea

**Report bug**:
1. Create GitLab issue with details
2. Tag: `@claude-code`, `bug`
3. Include: Error message, steps to reproduce, expected vs actual

**Suggest improvement**:
1. Create GitLab issue with proposal
2. Tag: `@claude-code`, `enhancement`
3. Include: Problem statement, proposed solution, rationale

**Feedback on these docs**:
1. Create GitLab issue or comment on this file
2. Be specific: What was confusing? What's missing?
3. We improve based on team feedback

---

## Summary

**You're now equipped to**:
- ✅ Understand why Claude Code is configured this way
- ✅ Use commands confidently (/quick-check, /full-check, etc.)
- ✅ Follow the 6-step workflow (Explore→Plan→Validate→Implement→Verify→Deliver)
- ✅ Respect the 3 principles (Progressive, Standardized, Measured)
- ✅ Navigate the 7-layer security model
- ✅ Track adoption metrics and success criteria
- ✅ Use sub-agents for complex analysis

**Next steps**:
1. **Read** [CLAUDE.md](../../CLAUDE.md) (all 9 blocks) — 20 min
2. **Run** `./scripts/check.sh quick` — 2 min (verify setup)
3. **Try** a simple task with Claude Code — 30 min
4. **Share feedback** with team — 5 min

**By day 90, Claude Code should be a normal part of your engineering stack.** 🚀

---

**Questions?** Slack: #dev-help | GitLab: @architecture | Docs: Read before asking

**Last Updated**: June 20, 2026 ✅
