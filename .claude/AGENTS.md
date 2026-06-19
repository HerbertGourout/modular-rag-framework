---
title: "Claude Code Custom Commands"
description: "Team-wide shortcuts for common development workflows"
applicableScopes: ["Development", "Testing", "Security", "CI/CD"]
commands:
  - name: "quick-check"
    scope: "validation"
  - name: "full-check"
    scope: "validation"
  - name: "validate-security"
    scope: "security"
  - name: "add-component"
    scope: "development"
  - name: "release"
    scope: "deployment"
---

# Claude Code Custom Commands

This file defines team-wide slash commands for common workflows in the Modular RAG Framework. These commands encapsulate complex validation, component creation, and deployment patterns.

---

## Available Commands

### `/quick-check` — Fast Local Validation

**Purpose**: Run syntax and import checks after code changes (< 30 seconds).  
**When to use**: After any file edit, before commit.  
**Equivalent command**: `./scripts/check.sh quick`

**What it validates**:
- ✅ Python syntax (ruff E, F rules)
- ✅ Import ordering (ruff I rule)
- ✅ Naming conventions (ruff N rule)

**Output**:
```
✓ Checking syntax and imports...
✓ All checks passed (0.8s)
```

**On failure**:
```
✗ Syntax error in src/modular_rag/ingestion/chunker.py:42
  - undefined name 'Chunker' (did you forget to import?)
```

---

### `/full-check` — Pre-Merge Validation

**Purpose**: Run comprehensive checks before creating a merge request (2-5 minutes).  
**When to use**: Before pushing to GitLab.  
**Equivalent command**: `./scripts/check.sh full`

**What it validates**:
- ✅ Syntax + imports (from `/quick-check`)
- ✅ Unit tests (tests/unit/)
- ✅ Contract conformance tests (tests/contract/)
- ✅ Code coverage report

**Output**:
```
✓ Quick checks passed (0.8s)
✓ Unit tests: 42 passed (2.1s)
✓ Contract tests: 8 passed (1.3s)
✓ Coverage: 92% (3.5s)
---
✓ All checks passed (7.7s)
```

**On failure**:
```
✗ Contract test failed: tests/contract/test_retriever_conformance.py::test_vector_retriever_protocol
  Expected isinstance(obj, VectorRetriever) — got MyCustomRetriever
```

---

### `/validate-security` — Security Layer Compliance

**Purpose**: Verify adherence to security rules and policies.  
**When to use**: Before security-sensitive changes.  
**Checks**:
- ✅ No hardcoded secrets (.env, API keys, credentials)
- ✅ No cross-domain imports (e.g., retrieval importing from generation)
- ✅ No unrestricted file access in adapters
- ✅ PII patterns in security module correct
- ✅ Lazy imports on heavy dependencies (qdrant-client, openai, etc.)

**Output**:
```
✓ Security layer validation

Secrets check:
  ✓ No hardcoded API keys found
  ✓ .env files properly gitignored
  
Cross-domain imports:
  ✓ src/modular_rag/ingestion/ has no generation imports
  ✓ src/modular_rag/retrieval/ has no generation imports
  
Adapter isolation:
  ✓ adapters/embeddings/ only imports core + contracts
  ✓ No domain module imports detected
  
Lazy imports:
  ✓ openai imported inside methods (5 locations)
  ✓ qdrant_client imported inside methods (3 locations)
  ✓ rank_bm25 imported inside methods (2 locations)
  
---
✓ All security checks passed
```

**On failure**:
```
✗ Security check failed

Cross-domain import detected:
  src/modular_rag/retrieval/hybrid_retriever.py:15
  from modular_rag.generation import PromptTemplate  ← BLOCKED
  
Reason: Retrieval cannot import from generation module
Fix: Pass PromptTemplate via constructor or use manifest config
```

---

### `/add-component` — Component Scaffolding Template

**Purpose**: Create a new component (chunker, retriever, generator, metric) with full scaffolding.  
**When to use**: Adding a new adapter or domain implementation.  
**Prompts**:
```
What type of component? (Choose one)
  1. Chunker (ingestion/)
  2. Retriever (retrieval/)
  3. Reranker (retrieval/)
  4. Generator (generation/)
  5. Metric/Scorer (eval/)
  6. Embedder (adapters/embeddings/)
  7. Vector store (adapters/vectorstores/)

Component name? (e.g., "bm25_retriever")

Description? (One sentence describing what it does)
```

**Output**: Creates full structure:
```
✓ Scaffolding new component: BM25Retriever

Created:
  ✓ src/modular_rag/retrieval/bm25_retriever.py
  ✓ tests/unit/retrieval/test_bm25_retriever.py
  ✓ tests/contract/test_bm25_retriever_conformance.py
  ✓ Stubs for Protocol implementation

Next steps:
  1. Implement Protocol in src/modular_rag/retrieval/bm25_retriever.py
  2. Write unit tests in tests/unit/retrieval/test_bm25_retriever.py
  3. Add conformance test using isinstance(obj, VectorRetriever)
  4. Register in orchestration/_default_factories.py
  5. Run /full-check before merge
```

---

### `/release` — Pre-Release Validation

**Purpose**: Comprehensive checks before release (all scopes).  
**When to use**: Before tagging a release.  
**Equivalent command**: `./scripts/check.sh all`

**What it validates**:
- ✅ All syntax + unit + contract checks (`/full-check`)
- ✅ Integration tests (requires Qdrant on localhost:6333)
- ✅ E2E tests (requires LLM API key)
- ✅ Documentation build
- ✅ CHANGELOG.md updated
- ✅ Version bumped in pyproject.toml
- ✅ ADR written (if structural changes)

**Output**:
```
✓ Release validation checklist

Pre-checks:
  ✓ Branch is main or release/* branch
  ✓ Working directory is clean
  ✓ Latest changes from origin/main pulled
  
Full validation:
  ✓ Quick checks passed (0.8s)
  ✓ Unit tests: 42 passed (2.1s)
  ✓ Contract tests: 8 passed (1.3s)
  ✓ Coverage: 92% (3.5s)
  ✓ Integration tests: 5 passed (4.2s) [Qdrant required]
  ✓ E2E tests: 3 passed (6.1s) [LLM API key required]
  
Documentation:
  ✓ docs/ builds successfully
  ✓ CHANGELOG.md has [Unreleased] entries → versions 1.0.5
  ✓ ADRs: 0001-0003 up to date
  
Final checks:
  ✓ pyproject.toml version: 1.0.5
  ✓ No untracked secrets (.env.local, etc.)
  
---
✓ Ready for release 1.0.5
Next: git tag v1.0.5 && git push --tags
```

**On failure**:
```
✗ Release check failed

Issue:
  CHANGELOG.md has no [Unreleased] section
  
Fix:
  1. Edit CHANGELOG.md
  2. Add [Unreleased] section at top
  3. List changes since last release
  4. Run /release again
```

---

## How to Use These Commands

### In Claude Chat

Type a command directly in chat:

```
/quick-check
```

Claude will execute the equivalent shell command and report results.

### Example Workflow

```
1. You make code changes
   → git add -A

2. Run immediate check
   /quick-check
   
3. All syntax OK, now validate fully
   /full-check
   
4. Tests pass, verify security rules
   /validate-security
   
5. All green, commit and push
   → git commit -m "feat: Add BM25Retriever"
   → git push origin feature/bm25-retriever
   
6. MR created, CI/CD auto-runs
   → (same checks happen in .gitlab-ci.yml)
   
7. After review, merge to main
   → git merge --squash
   
8. Before release, run final check
   /release
```

---

## Commands vs. Hooks

**Commands** (this file):
- Manual invocation: `/quick-check`
- Developer-triggered validation
- Immediate feedback in chat

**Hooks** (in `.claude/settings.json`):
- Automatic invocation after file writes
- PostToolUse: ruff linting after every edit
- No user interaction needed

**Together**:
- Hooks catch errors immediately (fail-fast)
- Commands validate at workflow stages (pre-commit, pre-merge, pre-release)

---

## Adding New Commands

To add a custom command to this team:

1. **Propose in GitLab issue**: Describe the workflow
2. **Get approval**: From @architecture team
3. **Update this file**: Add command definition
4. **Update scripts**: Add corresponding shell script or checklist
5. **Document**: Include in CONTRIBUTING.md if it's a critical workflow

**Template for new commands**:

```markdown
### `/command-name` — Short Description

**Purpose**: One-liner.  
**When to use**: Common scenario.  
**Equivalent command**: Shell equivalent.  
**What it validates**: Bulleted list.

**Output**: Example success output.

**On failure**: Example failure + fix.
```

---

## References

- **Validation scopes**: [docs/guides/validation.md](validation.md)
- **Validation protocol**: [docs/guides/validation-protocol.md](validation-protocol.md)
- **Security layers**: [.claude/rules/security-layers.md](../../.claude/rules/security-layers.md)
- **Git workflow**: [CONTRIBUTING.md](../../CONTRIBUTING.md#git-workflow-strategy)
