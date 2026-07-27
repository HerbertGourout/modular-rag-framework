# Developer Guides — Complete Reference

**For**: All team members (developers, architects, product managers, stakeholders)  
**Updated**: June 21, 2026  
**Status**: Production Ready ✅

---

## 🚀 Getting Started (Start Here!)

| Guide | Time | Purpose | For |
|-------|------|---------|-----|
| **[Framework Overview & Onboarding](./framework-overview-onboarding.md)** | 20 min | Complete vision: present + future features, why it matters, quick start by role | Everyone |
| **[Onboarding — Functional Profiles](../onboarding.md)** | 15 min | Which docs to read for your role (developer, tech lead, delivery consultant, functional/business, security) and the V1→V5 journey in plain language | Everyone (overlaps with the guide above — read either first) |
| **[Code Walkthrough 🆕](./code-walkthrough.md)** | 30 min | Progressive guided tour of the codebase: follow a query and a document through every module | Developers |
| **[Getting Started](./getting-started.md)** | 15 min | First-time setup + development environment | Developers |
| **[Installation](./installation.md)** | 10 min | Install dependencies for V1-V5 | Developers |
| **[Onboarding — Claude Code](./onboarding-claude-code.md)** | 1 day | Full team onboarding with productivity goals | Teams |

---

## 📖 Main Guides (Read These)

### Claude Code Configuration & Usage

| Guide | Lines | Purpose | Audience |
|-------|-------|---------|----------|
| **[CLAUDE CODE COMPLETE GUIDE](./CLAUDE-CODE-COMPLETE-GUIDE.md)** | 300 | High-level overview + 7-layer security | All devs |
| **[Complete Development Guide 🆕](./claude-code-complete-development-guide.md)** | 2,500 | End-to-end workflow with real examples | All devs |
| **[Settings Reference](./claude-code-settings-reference.md)** | 1,500 | All 100+ settings, scopes, precedence | Config leads |
| **[MCP Setup](./claude-code-mcp-setup.md)** | 1,000 | Model Context Protocol integration | Integration |
| **[Plugins & Marketplaces](./claude-code-plugins-marketplaces.md)** | 1,000 | Team plugin distribution | DevOps |
| **[Advanced Configuration](./claude-code-advanced-config.md)** | 800 | Subagents, skills, hooks | Advanced users |
| **[Enterprise Deployment](./claude-code-enterprise-deployment.md)** | 600 | MDM, Group Policy, managed settings | IT/DevOps |

### Architecture & Development Patterns

| Guide | Purpose | Audience |
|-------|---------|----------|
| **[Parallelization & Orchestration 🆕](./claude-code-parallelization-orchestration.md)** | Tool/component/agentic parallelization (500+ lines) | All devs |
| **[Validation Reference](./validation.md)** | Commands + scripts reference | All devs |
| **[Validation Protocol](./validation-protocol.md)** | Formal test scopes (unit/contract/integration/e2e) | Tech leads |
| **[Plugin Development](./plugin-development.md)** | Create custom plugins | Advanced users |
| **[Working with Agents](./working-with-agents.md)** | V2+ agent patterns (reference) | Architects |
| **[Sub-Agents & Parallelization](./subagents-parallelization.md)** | Advanced Claude patterns | Advanced users |

### Operations & Observability

| Guide | Purpose | Audience |
|-------|---------|----------|
| **[Adoption Metrics](./adoption-metrics.md)** | Track adoption + success KPIs | Tech leads |
| **[Observability](./observability.md)** | Logging, tracing, monitoring | Devops/Architects |
| **[MCP Integrations](./mcp-integrations.md)** | External tools integration process | Architects |
| **[Deployment](./deployment.md)** | Production deployment guide | DevOps |
| **[Audit & Traceability](./audit-traceability.md)** | Compliance + logging | Security/Compliance |

---

## 🎯 Quick Navigation by Need

### "I'm new and want to understand the full vision (framework + features)"
1. [Framework Overview & Onboarding](./framework-overview-onboarding.md) (20 min) ← **START HERE**
2. [ROADMAP.md](../../ROADMAP.md) (15 min) — Version timeline
3. [business-case.md](../business-case.md) (10 min) — Why it matters
4. [CLAUDE.md](../../CLAUDE.md) (30 min) — Project rules

### "I'm a new developer, where do I start?"
1. [Getting Started](./getting-started.md) (15 min)
2. [Onboarding — Claude Code](./onboarding-claude-code.md) (1 day)
3. [Complete Development Guide](./claude-code-complete-development-guide.md) (Read sections 1-4 first)

### "I want to build a feature"
1. [Complete Development Guide](./claude-code-complete-development-guide.md) — The Complete Workflow
2. [Validation Reference](./validation.md) — Commands reference
3. CLAUDE.md (in root) — Non-negotiable rules

### "I want to understand all configuration"
1. [CLAUDE CODE COMPLETE GUIDE](./CLAUDE-CODE-COMPLETE-GUIDE.md) — Overview
2. [Settings Reference](./claude-code-settings-reference.md) — All settings
3. [MCP Setup](./claude-code-mcp-setup.md) — MCP configuration
4. [Advanced Configuration](./claude-code-advanced-config.md) — Subagents, hooks, skills
5. [Parallelization & Orchestration](./claude-code-parallelization-orchestration.md) — Tool/component/agentic levels

### "I'm setting up for my team"
1. [Enterprise Deployment](./claude-code-enterprise-deployment.md) — MDM/Group Policy
2. [Plugins & Marketplaces](./claude-code-plugins-marketplaces.md) — Team plugins
3. [Adoption Metrics](./adoption-metrics.md) — Track success
4. [Onboarding — Claude Code](./onboarding-claude-code.md) — Team training

### "I'm integrating external tools"
1. [MCP Setup](./claude-code-mcp-setup.md) — MCP servers
2. [MCP Integrations](./mcp-integrations.md) — Integration process
3. [Advanced Configuration](./claude-code-advanced-config.md) — Custom plugins

### "I'm debugging a failing test"
1. [Validation Reference](./validation.md) — Test commands
2. [Complete Development Guide](./claude-code-complete-development-guide.md) — Debugging section
3. [Validation Protocol](./validation-protocol.md) — Test scopes

### "I want to use Claude Code subagents for RAG development"
1. [Advanced Configuration](./claude-code-advanced-config.md) — Subagents overview
2. [.claude/AGENTS.md](../.claude/AGENTS.md) — 8 domain-specialized subagents
3. [Parallelization & Orchestration](./claude-code-parallelization-orchestration.md) — Parallel execution patterns

---

## 📊 Content Map by Category

### Overview & Strategy (NEW - Framework Foundation)
- **[Framework Overview & Onboarding](./framework-overview-onboarding.md)** (3,000+ lines)
  - What the framework is and why it exists
  - V1 status (now) + V2-V5 roadmap
  - Quick start by role (developers, architects, PM, QA, DevOps)
  - Business impact and strategic features
  - One-page reference for everything

### Configuration (5 guides, 5,900 lines)
- Complete system of 5 scopes, 100+ settings, MCP integration, plugins, enterprise deployment

### Development (3 guides, 4,300 lines)
- End-to-end workflow with patterns, real examples, troubleshooting, parallelization orchestration

### Specialized Agents & Skills (2 collections)
- **8 Domain Subagents** (retrieval, ingestion, generation, security, architecture, testing, orchestration, observability)
- **8 Reusable Skills** (add-retriever, add-generator, validate-architecture, optimize-chunking, etc.)
- See: [.claude/agents/](../../.claude/agents/) and [.claude/skills/](../../.claude/skills/)

### Operations (5 guides)
- Deployment, observability, audit, metrics, integrations

### Reference (2 guides)
- Validation commands, test protocols

---

## 🔑 Key Concepts

### The 5-Minute Start

```bash
# 1. Install
pip install -e ".[v1,dev]"

# 2. Quick check (validate environment)
./scripts/check.sh quick

# 3. Read CLAUDE.md blocks 1-5 (20 min)
cat CLAUDE.md

# → You can now start building!
```

### The Complete Workflow (See Complete Development Guide)

```
1. EXPLORE (5-15 min)   — Read docs, understand rules
2. DESIGN (10-15 min)   — Choose architecture, plan
3. IMPLEMENT (30-45 min)— Generate code + tests
4. VALIDATE (5-15 min)  — Run checks, verify
5. REVIEW (15-30 min)   — Self-check, commit
```

### Architecture Golden Rules

```
✅ Hexagonal layering (one direction)
✅ Lazy imports (heavy libs inside methods)
✅ Wire via YAML + registry (not Python)
✅ Emit TraceSteps (observability)
✅ Never cross-domain (retrieval ≠ generation)
✅ Test everything (unit + contract)
✅ Type hints everywhere
```

---

## 📋 All Guides Checklist

### Core Configuration
- ✅ CLAUDE-CODE-COMPLETE-GUIDE.md (Overview + 7-layer security)
- ✅ claude-code-settings-reference.md (1,500 lines)
- ✅ claude-code-mcp-setup.md (1,000 lines)
- ✅ claude-code-plugins-marketplaces.md (1,000 lines)
- ✅ claude-code-advanced-config.md (800 lines)
- ✅ claude-code-enterprise-deployment.md (600 lines)

### Development & Architecture
- ✅ claude-code-complete-development-guide.md 🆕 (2,500 lines)
- ✅ Getting Started (Installation guide)
- ✅ Onboarding (1-day productivity path)
- ✅ Validation Reference (Commands)
- ✅ Validation Protocol (Test scopes)
- ✅ Plugin Development (Custom plugins)
- ✅ Working with Agents (V2+ reference)
- ✅ Sub-Agents & Parallelization (Advanced)

### Operations & Compliance
- ✅ Deployment (Production guide)
- ✅ Observability (Monitoring + logging)
- ✅ Adoption Metrics (Success tracking)
- ✅ Audit & Traceability (Compliance)
- ✅ MCP Integrations (External tools)

---

## 🆕 Latest Addition

### [Complete Development Guide](./claude-code-complete-development-guide.md) 🆕

**2,500 lines** covering the complete development workflow:

1. **Getting Started in 5 Minutes** — Prerequisites, rules, commands
2. **The Complete Workflow** — 5-phase EXPLORE → DESIGN → IMPLEMENT → VALIDATE → REVIEW
3. **Architecture Rules** — Hexagonal layering, lazy imports, registry pattern, observability
4. **Pattern Library** — Reusable solutions for retrievers, guards, generators, metrics
5. **Real-World Examples** — Complete examples (BM25, PII redaction) with step-by-step
6. **Validation & Testing** — Test scopes, checklist
7. **Debugging & Troubleshooting** — Common errors, root causes, fixes
8. **Anti-Patterns** — What NOT to do (with corrections)
9. **Quick Reference Card** — Commands, checklist, templates

**Perfect for**: New developers, feature implementation, troubleshooting

---

## 🚀 Getting Help

**Question**: "How do I...?"

| Question | See |
|----------|-----|
| Set up my environment | [Getting Started](./getting-started.md) |
| Build a feature | [Complete Development Guide](./claude-code-complete-development-guide.md) |
| Validate my code | [Validation Reference](./validation.md) |
| Debug a failing test | [Complete Development Guide — Debugging](./claude-code-complete-development-guide.md#debugging--troubleshooting) |
| Configure Claude Code | [Settings Reference](./claude-code-settings-reference.md) |
| Integrate GitHub/Slack | [MCP Setup](./claude-code-mcp-setup.md) |
| Set up team plugins | [Plugins & Marketplaces](./claude-code-plugins-marketplaces.md) |
| Deploy to production | [Deployment](./deployment.md) |
| Track adoption metrics | [Adoption Metrics](./adoption-metrics.md) |

---

## 📞 Support

**For questions about**:
- Development workflows → [Complete Development Guide](./claude-code-complete-development-guide.md)
- Architecture decisions → See `docs/adr/`
- Configuration → [Settings Reference](./claude-code-settings-reference.md)
- Observability → [Observability](./observability.md)
- Deployment → [Deployment](./deployment.md)
- Security → See `CLAUDE.md` block 07 + `docs/adr/0003-security-and-governance.md`

---

## 📅 Last Updated

**June 20, 2026** — Complete development guide added (2,500 lines). All configuration guides complete (5,900 lines). Total: ~11,000 lines of comprehensive documentation.
