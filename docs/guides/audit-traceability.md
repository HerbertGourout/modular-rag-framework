# Audit & Traceability Guidelines

This document defines how the Modular RAG framework maintains traceability for security, compliance, and debugging purposes.

---

## Session Traceability

### What Gets Logged

Every Claude Code session automatically logs:

```
Session ID: [UUID]
Start time: [ISO 8601]
End time: [ISO 8601]
Tools used: [list]
Files accessed: [list]
Decisions: [approve/reject/skip]
Errors: [list]
```

### Accessing Session Logs

Corrected 2026-08-06 — this section previously described GitHub Copilot Chat's storage
location, a different product, not Claude Code's.

**Local session transcripts** (one file per session, newline-delimited JSON):
```bash
ls ~/.claude/projects/<project-path-hash>/*.jsonl
```

**Auto-generated project memory** (persistent notes carried across sessions for this project):
```bash
ls ~/.claude/projects/<project-path-hash>/memory/
```

### Session Retention

Retention policy for local transcripts and any server-side logging is set by your Claude Code
installation/organization configuration, not by this project — check your actual Claude Code
settings rather than assuming a specific number of days here.

---

## Git Traceability

### Atomic Commits

Every commit must represent **one logical change**.

```bash
✅ GOOD: "feat: Add BM25Retriever adapter"
✅ GOOD: "fix: Prevent PII redaction timeout"
✅ GOOD: "docs: Update CLAUDE.md with security rules"

❌ BAD: "Update stuff"
❌ BAD: "feat: Add adapter + fix security + update docs" (mixed)
❌ BAD: "WIP" (unclear)
```

### Commit Message Format

```
<type>: <subject>

<body (optional)>
<footer (optional)>
```

**Types**:
- `feat` — New feature or adapter
- `fix` — Bug fix
- `docs` — Documentation
- `refactor` — Code restructuring (no behavior change)
- `test` — Test additions
- `chore` — Dependencies, config changes

**Example**:
```
feat: Add PII redaction with SSN pattern matching

Implements RegexRedactor with configurable patterns for:
- Social Security Numbers (###-##-####)
- Credit card numbers (####-####-####-####)
- Email addresses (user@domain.com)

Adds:
- security/redaction/regex_redactor.py
- tests/unit/security/redaction/test_regex.py
- conformance test in tests/contract/

Fixes #127
```

### Viewing Git History

```bash
# See who changed what
git log --oneline -- src/modular_rag/security/

# See full commit details
git show abc123

# See blame (who changed each line)
git blame src/modular_rag/security/policies.py

# See changes between versions
git log -p --follow -- .claude/settings.json

# Find commits touching certain keywords
git log --all --grep="security" --oneline
```

---

## PR Traceability

### Required PR Information

**Title**:
```
[Scope] Brief description

Examples:
- [security] Add API key rotation validation
- [retrieval] Implement LLM-based reranker
- [docs] Update architecture guide for V2
```

**Description** (use template from CONTRIBUTING.md):
```markdown
## Description
What does this PR do?

## Type of change
- [ ] New feature
- [ ] Bug fix
- [ ] Documentation

## Scope
List affected modules

## Checklist
- [ ] Tests added/updated
- [ ] No cross-domain imports
- [ ] CLAUDE.md rules respected
- [ ] Passes CI/CD

## Notes
Any other context
```

### PR Approval Chain

```
1. Author creates PR (Draft if WIP)
   ↓
2. CI/CD runs automatically
   - Lint (ruff)
   - Unit tests
   - Contract tests
   - Coverage
   ↓
3. Peer code review (1+ reviewer)
   - Architecture compliance?
   - Code quality?
   - Security concerns?
   ↓
4. Security sign-off (if sensitive)
   - Policy changes?
   - New secret handling?
   - Third-party integration?
   ↓
5. Approved → Merge
   - Squash (default for features)
   - Rebase (for documentation)
   ↓
6. Delete branch
   - Cleaned up automatically
```

### Viewing PR History

```bash
# List all PRs (GitHub CLI)
gh pr list --state all

# View specific PR with approval chain
gh pr view 42

# See all PRs touching security/
gh pr list --search "label:security"

# See PRs by author
gh pr list --author @username

# Download PR as patch
gh pr diff 42 > feature.patch
```

---

## Configuration Versioning

### Files Requiring Change Tracking

| File | Who Reviews | Change Frequency |
|------|------------|-----------------|
| `.claude/settings.json` | Security team | Rare (permission changes) |
| `.claude/.instructions.md` | Architecture team | Rare (rule changes) |
| `.github/workflows/ci.yml` | DevOps team | Occasional (test scope changes) |
| `CONTRIBUTING.md` | Team lead | Occasional (process changes) |
| `pyproject.toml` | Release manager | Regular (dependency updates) |
| `docs/adr/` | Architecture team | As needed (decisions) |
| `CLAUDE.md` | Project owner | Regular (scope updates) |

### Tracking Changes

**Commit every change**:
```bash
# Before editing config
git checkout -b fix/security-policy-update

# Make changes
# ...

# Commit with clear message
git commit -m "chore: Update .claude/settings.json with new API restriction

- Added new_api_path to permissions.deny (V3 scope)
- Reduced timeout for Qdrant operations
- Clarified permissions.ask documentation

Reason: Prevent accidental V3 implementation in V1"

# Push and create PR
git push origin fix/security-policy-update
```

**Query changes**:
```bash
# Who changed settings last?
git log --oneline -n 10 -- .claude/settings.json

# What changed in settings?
git diff HEAD~1 .claude/settings.json

# When was this setting added?
git log -p --all -S "SETTING_NAME" -- .claude/settings.json | head -50
```

---

## Compliance Audit Checklist

Use this checklist for security audits and compliance reviews:

### Code Changes
- [ ] No hardcoded secrets (API keys, tokens, passwords)
- [ ] No cross-domain imports between modules
- [ ] PII patterns use compiled regex with timeout
- [ ] All TraceStep emissions are PII-safe
- [ ] New contracts have matching tests
- [ ] No deprecated dependencies

### Documentation Changes
- [ ] CLAUDE.md updated if scope/rules changed
- [ ] ADR written if architectural decision made
- [ ] CHANGELOG.md updated
- [ ] docs/guides/ updated if process changed

### Security Changes
- [ ] Security review sign-off
- [ ] Policy changes documented in ADR
- [ ] New adapters use lazy imports
- [ ] Secrets never logged or exposed
- [ ] MCP integration approved (if applicable)

### Testing Changes
- [ ] Unit tests added for new code
- [ ] Contract tests verify Protocol compliance
- [ ] Integration tests with Qdrant passing
- [ ] E2E tests passing (if applicable)
- [ ] Coverage maintained (90%+)

### Git Hygiene
- [ ] Commits are atomic and descriptive
- [ ] Branch named per convention (feature/, fix/, docs/)
- [ ] PR description filled
- [ ] All CI/CD checks pass
- [ ] Code reviewed by 2+ people (if security)

---

## Audit Reports

### Generating an Audit Report

**Scope: All changes by date range**
```bash
# All commits between dates
git log --oneline --all \
  --since="2026-05-01" \
  --until="2026-06-01" \
  | head -50

# Export with details
git log --pretty=fuller \
  --since="2026-05-01" \
  --until="2026-06-01" \
  > audit_report_may.txt
```

**Scope: All changes to security module**
```bash
# Find all security-related commits
git log --all --grep="security" --oneline

# See all changes to security/ folder
git log --oneline -- src/modular_rag/security/

# Export full diff
git log -p -- src/modular_rag/security/ > security_changes.patch
```

**Scope: All secret-related incidents**
```bash
# Find commits that might have exposed secrets
git log --all -S "MRAG_" --oneline
git log --all -S "API_KEY" --oneline
git log --all -S "sk-" --oneline  # OpenAI key pattern

# Examine specific commit
git show abc123 | grep -i "key\|secret\|token"
```

### Creating Compliance Evidence

For SOC2, GDPR, or other compliance:

```bash
# Evidence 1: All config changes
git log --oneline -- .claude/settings.json CONTRIBUTING.md .github/workflows/ci.yml > config_history.txt

# Evidence 2: All PR approvals (export from GitHub)
gh pr list --state merged --search "created:>=2026-01-01" --json number,title,mergedAt,reviews > pr_approvals.json

# Evidence 3: All security commits
git log --all --grep="security\|guard\|policy" --oneline > security_commits.txt

# Evidence 4: No secrets in git
git log -p -S "sk-" --all | wc -l  # Should be 0
```

---

## Key Monitoring Points

### Pre-Commit Hooks (Optional)

Add to `.git/hooks/pre-commit` to prevent accidental commits:

```bash
#!/bin/bash
# Prevent .env from being committed
if git diff --cached --name-only | grep -q "^\.env$"; then
  echo "ERROR: .env file staged for commit (contains secrets)"
  exit 1
fi

# Prevent API key patterns
if git diff --cached -S "sk-" | grep -q "+.*sk-"; then
  echo "ERROR: OpenAI key pattern detected in staged changes"
  exit 1
fi

exit 0
```

**Install**:
```bash
chmod +x .git/hooks/pre-commit
```

### CI/CD Checks

`.github/workflows/ci.yml` should enforce:

```yaml
security_check:
  script:
    # Scan for secrets
    - |
      if git log -p -S "sk-\|MRAG_.*=" HEAD~1 | grep -q "+"; then
        echo "ERROR: Secrets detected in commits"
        exit 1
      fi
```

---

## References

- [CLAUDE.md](../../CLAUDE.md) — Project policies
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Git workflow
- [.claude/rules/security-layers.md](../../.claude/rules/security-layers.md) — 7-layer security strategy
- [.gitignore](../../.gitignore) — Secret patterns
- [docs/adr/](../../docs/adr/) — Architectural decisions

