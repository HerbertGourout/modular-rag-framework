# Onboarding: Using Claude Code on Modular RAG Framework

Welcome! This guide walks you through setting up and using Claude Code for the first time on this project. By the end, you'll understand how to work efficiently with AI assistance while maintaining code quality and project standards.

**Time estimate**: 20 minutes  
**Required**: VS Code, GitHub/GitLab access, Python 3.11+

---

## Prerequisites

### 1. Install Claude Code Extension
- Open VS Code
- Go to Extensions (Ctrl+Shift+X / Cmd+Shift+X)
- Search: "GitHub Copilot Chat"
- Click Install
- Sign in with your GitHub account
- You should see a Copilot icon (💬) in the left sidebar

### 2. Clone and Set Up the Project

```bash
git clone https://pscode.lioncloud.net/data_specialiste/advancedpublicisrag.git
cd modular-rag-framework

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[v1,dev]"
```

### 3. Verify Your Setup

```bash
# Quick validation (should pass in < 30s)
./scripts/check.sh quick

# Output should be:
# ✓ Checking syntax and imports...
# ✓ All checks passed (0.8s)
```

If you see errors, check:
- [ ] Python 3.11+ installed
- [ ] Virtual environment activated
- [ ] `pip install -e .[v1,dev]` ran successfully

---

## Understanding the Project Structure

Before using Claude Code, understand how this project is organized:

### Hexagonal Layering (One-Direction Flow)

```
cli/ + api/  →  app/  →  orchestration/  →  contracts/ + core/
                                              ↑
                        domain modules  ─────┘
                        (ingestion, retrieval, generation, security, agents, memory, eval)
                                              ↑
                        adapters/  ──────────┘
```

**Key rule**: Modules can only import from layers below them. Domain modules **never** import from each other.

### Core Files You Need to Know

| File | Purpose | Read First? |
|------|---------|-----------|
| [CLAUDE.md](../../CLAUDE.md) | Project rules (9 blocks) | ✅ YES |
| [.claude/.instructions.md](./../.instructions.md) | Claude's mandatory rules | ✅ YES (sections 1-5) |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Git workflow, branching, MR process | ✅ YES |
| [.claude/settings.json](./../settings.json) | Permissions, hooks configuration | 🟡 REFERENCE ONLY |
| [docs/guides/validation.md](validation.md) | Command reference | 🟡 REFERENCE ONLY |

---

## Your First Task: Add a Simple Component

Let's walk through a real example: **Adding a new text chunker**.

### Step 1: Understand the Requirement

**Task**: Add a `WordCountChunker` that chunks text by word count instead of character count.

**Files to read first**:
1. [src/modular_rag/contracts/chunking.py](../../src/modular_rag/contracts/chunking.py) — What does a Chunker Protocol look like?
2. [src/modular_rag/ingestion/chunkers/fixed.py](../../src/modular_rag/ingestion/chunkers/fixed.py) — Existing chunker implementation

**Questions to ask yourself**:
- What inputs does a Chunker need? (text, word_count)
- What outputs? (list of Chunk objects)
- Does Protocol need changes? (usually no for new implementations)

### Step 2: Ask Claude Code to Explore

Open the Copilot Chat (💬) and ask:

```
I need to add a WordCountChunker to src/modular_rag/ingestion/chunkers/.
First, explore:
1. The Chunker Protocol in contracts/chunking.py
2. How FixedChunker is implemented
3. Where chunkers are registered
4. Test patterns for chunkers

Then show me the structure I should follow.
```

**Claude's response** should include:
- Protocol definition
- Implementation template
- Registration pattern
- Test template

### Step 3: Create the Implementation

Ask Claude:

```
Now create:
1. src/modular_rag/ingestion/chunkers/word_count.py implementing WordCountChunker
2. tests/unit/ingestion/chunkers/test_word_count.py with basic tests
3. Add WordCountChunker to orchestration/_default_factories.py

Follow the Chunker Protocol exactly. Use name="word-count" for registration.
```

**Review Claude's output carefully:**
- [ ] Does it import only from `contracts/` and `core/`?
- [ ] Does it implement all required Protocol methods?
- [ ] Are unit tests comprehensive?
- [ ] Is the factory registration correct?

### Step 4: Validate Locally

Before committing, run:

```bash
# Quick syntax check
./scripts/check.sh quick

# Full validation (unit + contract tests)
./scripts/check.sh full

# Both should pass
```

If tests fail:
- Read the error message carefully
- Ask Claude to fix it: "The test is failing because... How do I fix it?"
- Run validation again

### Step 5: Create a Branch and Commit

```bash
# Create feature branch
git checkout -b feature/word-count-chunker

# Stage all changes
git add -A

# Commit with clear message
git commit -m "feat: Add WordCountChunker adapter

Implements word-count-based text chunking as alternative to fixed character chunking.

Adds:
- WordCountChunker in src/modular_rag/ingestion/chunkers/word_count.py
- Unit tests in tests/unit/ingestion/chunkers/test_word_count.py
- Registration in orchestration/_default_factories.py

Protocol: Implements Chunker.chunk() and Chunker.name()
Tests: 5 unit tests covering edge cases
"

# Push to GitLab
git push origin feature/word-count-chunker
```

### Step 6: Create MR and Get Review

On GitLab:
1. Create Merge Request (auto-filled with your branch)
2. Fill MR template:
   - Description: "Adds word-count-based text chunking"
   - Type: ✅ New feature
   - Scope: ingestion/chunkers/
   - Checklist: mark all ✅
3. Request review from @maintainer
4. Wait for CI/CD to pass + human review
5. Merge when approved

---

## Daily Workflow: Using Claude Code Effectively

### ✅ DO: Use Claude Code For...

| Task | How | Command |
|------|-----|---------|
| Explore module structure | Ask Claude to map it | "Explore src/modular_rag/retrieval/ and list all classes" |
| Implement a new adapter | Follow 6-step workflow | /add-component → implement → test → review |
| Debug a failing test | Ask Claude to analyze | "Why is this test failing? src/test_xyz.py:42" |
| Refactor module code | Incremental changes | Work on 1 file at a time, validate after each |
| Generate boilerplate | Ask for template | "Generate unit test template for Retriever" |

### ❌ DON'T: Avoid These Patterns

| Mistake | Why It's Bad | Better Approach |
|---------|-------------|-----------------|
| Ask Claude to implement huge features at once | Creates messy commits, hard to review | Break into 3-4 smaller tasks |
| Ignore validation errors | Code passes locally but fails in CI | Always run `./scripts/check.sh full` |
| Mix bug fixes + features in one MR | Review becomes unclear | One MR = one topic (feature/ or fix/ branch) |
| Ask Claude to implement V2+ features | Reserved for future phases | Stick to V1 scope (ingestion, retrieval, generation, eval, security) |
| Use Claude as a code copilot only | Underuses AI capabilities | Use as agent + validator + reviewer + explorer |

---

## Common Questions

### Q: I'm not sure about the requirement. What should I do?

**A**: Use the 6-step workflow:

1. **Explore**: "Explore how X works in the codebase. Show me examples."
2. **Plan**: "Break this task into 3-4 concrete steps."
3. **Validate** (with human): "Does this plan look right? Should I change anything?"
4. **Implement**: "Now implement step 1: [task]"
5. **Verify**: Run `./scripts/check.sh full`
6. **Deliver**: Create MR

**Don't** jump straight to "implement the whole thing."

### Q: My code is failing tests. What do I do?

**A**:

1. **Read the error message**: What exactly is failing?
2. **Ask Claude**: "This test is failing: [error]. What's wrong and how do I fix it?"
3. **Review Claude's explanation**: Do you understand why it failed?
4. **Implement fix**: Apply the fix
5. **Validate again**: Run `./scripts/check.sh quick` to verify
6. **Learn**: Understand the root cause so you don't make the same mistake

### Q: Can I work on multiple features at once?

**A**: No. Create separate branches:

```bash
# Feature 1
git checkout -b feature/chunker-v2
# ... work ...
# ... push ...
# ... MR created ...

# Feature 2 (new branch from main)
git checkout main
git pull origin main
git checkout -b feature/retriever-cache
# ... work ...
```

Each branch = one topic. This makes reviews clean and easy to revert if needed.

### Q: What's the difference between `/quick-check` and `/full-check`?

**A**:

| Command | Time | Checks | When to Use |
|---------|------|--------|-----------|
| `/quick-check` | ~30s | Syntax + imports (ruff E,F,I) | After code edits, before commit |
| `/full-check` | 2-5m | Syntax + unit + contract tests + coverage | Before MR, before merge |

- Use **quick** while coding (fail-fast)
- Use **full** before pushing (comprehensive validation)

### Q: Can I use Claude Code for non-code tasks?

**A**: Yes, but with caution:

✅ **Good uses**:
- Understand architecture (ask Claude to explain hexagonal layering)
- Generate documentation (create test case explanations)
- Review code (ask Claude to review your implementation)

❌ **Avoid**:
- Asking Claude to rewrite entire modules
- Using Claude as the only reviewer (always get human review)
- Automating deployment (V4+ scope, not V1)

---

## Common Pitfalls to Avoid

### Pitfall 1: "I'll ask Claude to implement everything at once"

**Problem**: Creates huge commits that are hard to review and debug.

**Fix**: Break tasks into 30-minute chunks. Ask Claude to implement one piece at a time.

```
❌ "Implement the entire hybrid retriever with BM25, vector search, and reranking"
✅ "Implement BM25Retriever first. I'll add vector search as a separate task."
```

### Pitfall 2: "I don't understand the error, so I'll ask Claude to fix it randomly"

**Problem**: You learn nothing, and Claude might fix it wrong.

**Fix**: Ask Claude to explain first, then fix.

```
❌ Claude: "Try changing this line..." → You change it blindly
✅ Claude: "This fails because X. To fix it, you need to Y." → You understand and fix
```

### Pitfall 3: "I'll skip validation because my code looks fine"

**Problem**: Passes locally, fails in CI/CD. Wasted time.

**Fix**: Always validate before pushing.

```bash
./scripts/check.sh full  # Takes 2-5 min, saves 30 min of debugging
```

### Pitfall 4: "I'll work on multiple features in the same branch"

**Problem**: Hard to review, easy to introduce bugs, confuses git history.

**Fix**: One branch per feature.

```bash
git checkout -b feature/feature-1  # Work on feature 1
git commit...
git push...
# Create MR 1

git checkout main
git checkout -b feature/feature-2  # Separate branch for feature 2
```

---

## Getting Help

### If Something Breaks

1. **Check the error message** — usually tells you exactly what's wrong
2. **Ask Claude** — paste the error and ask "Why does this happen?"
3. **Check CLAUDE.md** — does your change violate a rule?
4. **Ask maintainer** — if still stuck, ask in #dev-help on Slack

### If You're Unsure About the Design

1. **Read the relevant ADR** — see [docs/adr/](../../docs/adr/)
2. **Ask Claude** — "According to ADR-0002, should I...?"
3. **Ask maintainer** — design decisions need human approval

### If You Want to Learn More

- 📖 [CLAUDE.md](../../CLAUDE.md) — All project rules
- 📖 [docs/architecture/overview.md](../architecture/overview.md) — Technical architecture
- 📖 [CONTRIBUTING.md](../../CONTRIBUTING.md) — Git workflow + MR process
- 📖 [docs/guides/validation.md](validation.md) — All validation commands
- 📖 [.claude/AGENTS.md](../../.claude/AGENTS.md) — Human-readable reference for the 8 subagents (not auto-loaded by Claude Code itself — the agents work because of `.claude/agents/*.md`); the actual invocable commands are the skills under `.claude/skills/*/SKILL.md`

---

## Next Steps

1. **Read CLAUDE.md blocks 1-5** (15 min) — understand project rules
2. **Run a quick validation** (2 min) — `./scripts/check.sh quick`
3. **Try adding a small component** (30 min) — follow the WordCountChunker example
4. **Ask for code review** — let maintainers give feedback
5. **Iterate and learn** — each task teaches you more

---

## Success Checklist

By the end of your first week, you should be able to:

- [ ] Understand hexagonal layering and why it matters
- [ ] Run validation scripts confidently (`quick`, `full`)
- [ ] Know when to ask Claude vs. when to ask humans
- [ ] Create a feature branch and MR without help
- [ ] Implement a small adapter (chunker, retriever, etc.)
- [ ] Write unit tests for your code
- [ ] Explain why cross-domain imports are forbidden
- [ ] Use /quick-check and /full-check appropriately

**If you can check all these boxes, you're ready to work independently with Claude Code!** 🚀
