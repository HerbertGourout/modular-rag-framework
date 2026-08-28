# Adoption Metrics & Success Dashboard

This guide defines how to measure Claude Code adoption and success on the Modular RAG Framework. Track these metrics to ensure the initiative delivers value and maintains quality.

**Read this as a template for a multi-person team, not a current-state report.** The examples
below (developer counts, weekly adoption percentages, multi-reviewer approval chains) assume a
team this project doesn't have today — the current, actual team size is one active developer
with sole decision authority (a target of up to a handful more, not yet assembled; see
[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)'s own authors line). Nothing here is
a claim about today's adoption numbers.

Use this framework once the team actually grows past one person. A single-developer project
should skip the team-adoption-rate metrics entirely and focus on the ones that still apply solo:
validation performance, test coverage, architecture violations.

---

## 90-Day Success Criteria

**Goal**: Claude Code becomes a normal part of the engineering stack — reproducible, governed, and appreciated by developers.

### By Day 30 (Foundation)

| Metric | Target | Status | Notes |
|--------|--------|--------|-------|
| Team trained | 100% | 🟡 In progress | All developers read CLAUDE.md + onboarding guide |
| CLAUDE.md read | 100% | 🟡 In progress | Every team member understands rules |
| First task completed | 3+ | 🟡 In progress | Team has tried Claude on real tasks |
| Bugs introduced | 0 | 🟡 TBD | No regressions from Claude-assisted code |
| Test coverage | 90%+ | ✅ Current state | Maintain during adoption |

### By Day 60 (Standardization)

| Metric | Target | Status | Notes |
|--------|--------|--------|-------|
| Team adoption rate | 50% | 🟡 In progress | Half the team uses Claude regularly |
| MRs with Claude input | 40%+ | 🟡 In progress | Substantial PRs credit Claude assistance |
| Validation time | <5 min | ✅ Target met | `./scripts/check.sh full` consistently fast |
| Test pass rate (CI/CD) | 95%+ | ✅ Target met | Main branch is stable |
| Code review time | -20% | 🟡 TBD | Reviews faster due to clear rules + documentation |
| Architecture violations | 0 | ✅ Target met | No cross-domain imports or direct wiring |

### By Day 90 (Maturity)

| Metric | Target | Status | Notes |
|--------|--------|--------|-------|
| Team adoption rate | 80%+ | 🟡 In progress | Most developers using Claude Code |
| Team velocity | +15% | 🟡 TBD | Commits per week, story points completed |
| Bug rate (Claude) | <2% | 🟡 TBD | Claude-assisted code introduces fewer bugs than human baseline |
| Test coverage | 92%+ | 🟡 Target | Slight improvement |
| Knowledge distribution | 3+ specialists | 🟡 In progress | Multiple team members can explain architecture |
| Onboarding time | <2 days | 🟡 In progress | New developers productive quickly |

---

## Key Performance Indicators (KPIs)

### 1. Task Completion Rate

**Definition**: % of Claude-assisted tasks that complete successfully (pass validation + MR review).

**How to measure**:
```
Success rate = (Completed tasks) / (Total tasks attempted) × 100%
```

**Target**: 85%+ by day 90

**Calculation**:
- ✅ Completed = task → /full-check passes → MR approved and merged
- ❌ Failed = task → validation fails multiple times → abandoned or human takeover
- 🟡 In Progress = active MR

**Tool**: Track in spreadsheet:
```
| Date | Task | Duration | Status | Result |
|------|------|----------|--------|--------|
| Jun 20 | Add BM25Retriever | 45 min | ✅ Merged | Success |
| Jun 21 | Fix circular imports | 30 min | ✅ Merged | Success |
| Jun 22 | Add GraphStore adapter | 120 min | ❌ Abandoned | Failed |
```

**Dashboard metric**: `Success Rate = 2/3 = 67%` (at day 22)

### 2. Bug Introduction Rate

**Definition**: % of bugs introduced by Claude-assisted code vs. human code baseline.

**How to measure**:
```
Claude bug rate = (Bugs from Claude PRs) / (Total Claude PR lines) × 1000
Human bug rate = (Bugs from human PRs) / (Total human PR lines) × 1000
```

**Target**: Claude bug rate ≤ Human bug rate (ideally 20% lower due to validation)

**Calculation example**:
- Claude PRs: 5,000 lines written, 2 bugs found → 0.4 bugs per 1000 lines
- Human PRs: 4,000 lines written, 3 bugs found → 0.75 bugs per 1000 lines
- **Result**: Claude is 47% better

**Tool**: Track bug origin in issue labels:
```
Labels: [claude-assisted] or [human-written]
When bug found: add label + regression note
```

### 3. Team Adoption Rate

**Definition**: % of team actively using Claude Code for tasks.

**How to measure**:
```
Adoption rate = (Active Claude users) / (Total developers) × 100%
```

**Active** = created ≥1 Claude-assisted PR in the last 30 days

**Calculation example**:
- Day 30: 3 out of 10 developers → 30% adoption
- Day 60: 5 out of 10 developers → 50% adoption
- Day 90: 8 out of 10 developers → 80% adoption

**Tool**: GitHub user filter on PRs:
```bash
# PRs mentioning Claude in last 30 days
git log --all --grep="claude\|claude code\|ai-assisted" --since="30 days ago" --format="%aN" | sort -u | wc -l
```

### 4. Validation Performance

**Definition**: Time to run full validation suite locally.

**How to measure**:
```
Validation time = time ./scripts/check.sh full
```

**Target**: <5 minutes

**Current performance** (from CLAUDE.md block 04):
- quick: ~30 seconds
- full: 2-5 minutes
- integration: 1-2 minutes (with Qdrant)
- e2e: 2-5 minutes (with LLM API)
- all: ~10 minutes

**Dashboard**: Track over time
```
| Week | Quick | Full | Integration | E2E | All |
|------|-------|------|-------------|-----|-----|
| W1   | 0.8s  | 3.2m | 1.5m        | 4.1m | 9.6m |
| W2   | 0.8s  | 3.0m | 1.4m        | 3.9m | 9.1m |
| W3   | 0.8s  | 2.9m | 1.3m        | 3.8m | 8.8m |
```

**Alert**: If any tier goes >10% slower, investigate (new dependencies? slow tests?)

### 5. Test Coverage

**Definition**: % of source code covered by automated tests.

**How to measure**:
```
Coverage = (Lines covered) / (Total lines) × 100%
```

**Target**: 90%+ by day 90 (current: 92%)

**Tool**: Already tracked in CI/CD
```bash
pytest --cov=src/modular_rag --cov-report=term-missing
```

**Dashboard**: Track in CHANGELOG or CI/CD dashboard

### 6. Code Review Time

**Definition**: Average time from MR creation to approval.

**How to measure**:
```
Review time = (MR approval time) - (MR creation time)
Average = mean(all review times)
```

**Target**: Reduce by 20% (from current ~6 hours to ~5 hours)

**Why**: Clear rules + validation = fewer review comments

**Tool**: GitHub API or manual tracking
```bash
# Example: track PR approval times
gh pr list --state all --json createdAt,updatedAt
```

### 7. Architecture Violations

**Definition**: # of errors caught by hooks or code review (cross-domain imports, direct wiring, lazy import violations).

**How to measure**:
```
Violations per week = count(cross-domain imports + direct wiring + other violations)
```

**Target**: 0 (protected by hooks + code review)

**Tool**: layering is automated by `scripts/check_layering.py --strict`; broader direct-wiring
and lazy-import review remains manual. `futureHooks` is not a real Claude Code key and no
`scripts/validate_imports.py` exists. Today, run the `validate-security` skill for the additional
grep-based checks:
```bash
# what the validate-security skill actually runs:
# - cross-domain imports: grep across ingestion/retrieval/generation/security/agents/memory/eval
# - direct wiring: grep for concrete component instantiation outside orchestration/ and tests/
# - lazy imports: grep for module-level "import qdrant_client/rank_bm25/openai/..."
```
If this becomes a real automated hook later, it would need an actual script wired into `hooks.PostToolUse` — not a `futureHooks` key.

---

## Reporting Dashboard

### Weekly Standup Template

```markdown
## Claude Code Adoption — Week X

**Period**: [Start] → [End]

### Key Metrics

| Metric | Week X | Target | Status |
|--------|--------|--------|--------|
| Task completion rate | 75% | 85%+ | 🟡 Tracking |
| Bug rate (Claude vs human) | 0.4/1k vs 0.7/1k | ≤ baseline | ✅ Better |
| Team adoption | 40% | 80% by D90 | 🟡 On track |
| Validation time (full) | 3.1m | <5m | ✅ Good |
| Test coverage | 91% | 90%+ | ✅ Good |
| Code review time | 5.8h | -20% | 🟡 Baseline |
| Architecture violations | 0 | 0 | ✅ Perfect |

### Highlights

- ✅ Task 1: [Description] — Completed successfully
- ✅ Task 2: [Description] — Merged with positive review
- 🟡 Task 3: [Description] — In progress, 50% done
- ❌ Task 4: [Description] — Abandoned, reason: [complexity]

### Blockers

- [Blocker 1]: Description + impact + proposed fix
- [Blocker 2]: Description + impact + proposed fix

### Next Week Focus

- [ ] Continue X feature
- [ ] Start Y adoption initiative
- [ ] Address blocker Z

**Prepared by**: [Name] | **Date**: [Date]
```

---

## Success Criteria by Adoption Phase

### Phase 1: Days 1-30 (Foundation)

**Goal**: Team understands rules and completes first tasks successfully.

**Success = ALL true**:
- [ ] 100% of team has read CLAUDE.md
- [ ] 100% of team has read onboarding guide
- [ ] ≥3 tasks completed with Claude assistance
- [ ] 0 bugs introduced by Claude PRs
- [ ] 0 architecture violations
- [ ] Test coverage maintained ≥90%

**Metrics to track**: Task completion rate, bugs, violations

### Phase 2: Days 31-60 (Standardization)

**Goal**: Claude Code becomes normal workflow; team is efficient.

**Success = ALL true**:
- [ ] 50%+ of team using Claude regularly
- [ ] 40%+ of MRs have Claude input
- [ ] Validation time <5 min consistent
- [ ] CI/CD test pass rate ≥95%
- [ ] Architecture violations = 0
- [ ] Code review time -10% vs baseline

**Metrics to track**: Adoption rate, validation time, review time, violations

### Phase 3: Days 61-90 (Maturity)

**Goal**: Claude Code is a proven asset; team is confident.

**Success = ALL true**:
- [ ] 80%+ of team using Claude regularly
- [ ] 60%+ of MRs have Claude input
- [ ] Team velocity +10% (commits/week, story points)
- [ ] Bug rate (Claude) ≤ bug rate (human)
- [ ] Onboarding time <2 days for new developers
- [ ] Knowledge distributed (3+ architecture experts)

**Metrics to track**: Team velocity, bug rate, knowledge distribution, onboarding time

---

## Reporting Cadence

| Frequency | Owner | Audience | Content |
|-----------|-------|----------|---------|
| **Daily** | Individual devs | Self | Personal standup: "What I did with Claude today" |
| **Weekly** | Tech lead | Team | Standup template (above) + blockers |
| **Bi-weekly** | Architect | Leadership | Summary: metrics trend, ROI, next phase |
| **Monthly** | PM | Stakeholders | Full dashboard: adoption, velocity, quality |

---

## Red Flags (When to Escalate)

### 🚨 Critical Issues

| Flag | Meaning | Action |
|------|---------|--------|
| Task completion <60% | More failures than successes | Pause new tasks; review failures; fix training |
| Bug rate 2x baseline | Claude-assisted code is buggy | Audit recent PRs; add more hooks; retrain |
| Adoption rate stuck at 20% | Team not adopting | 1:1 interviews; identify blockers; adjust training |
| Validation time >10 min | Build is slow | Profile; optimize tests or CI config |
| Test coverage <85% | Quality regressing | Require tests in PRs; code review focus |
| Architecture violations >5/week | Rules not working | Audit violations; strengthen hooks; retrain |

### 🟡 Minor Issues

| Flag | Meaning | Action |
|------|---------|--------|
| Code review time unchanged | Governance not helping | Unclear rules? → improve documentation |
| Knowledge stuck with 1 person | Bus factor risk | Pair programming; cross-train |
| Onboarding >3 days | Setup friction | Improve docs; automate setup |

---

## Dashboard: Monthly View

Use this template for monthly reporting:

```markdown
# Claude Code Adoption Dashboard — Month X

## KPI Summary

```
Completion rate:      [graph] 60% → 75% → 85% (↑ good)
Bug rate (Claude):    [graph] 0.6/1k vs 0.7/1k baseline (✅ good)
Team adoption:        [graph] 20% → 40% → 60% (↑ on track)
Validation time:      [graph] 3.5m → 3.2m → 3.0m (↓ good)
Test coverage:        [graph] 89% → 90% → 91% (↑ good)
Code review time:     [graph] 6.5h → 6.0h → 5.8h (↓ good)
Architecture violations: [graph] 2 → 1 → 0 (✅ perfect)
```

## Key Wins

- ✅ [Win 1]: Impact + metrics
- ✅ [Win 2]: Impact + metrics

## Challenges

- 🟡 [Challenge 1]: Impact + plan
- 🟡 [Challenge 2]: Impact + plan

## Next Month

- [ ] Focus area 1
- [ ] Focus area 2
- [ ] Address challenge X

**Prepared by**: [Name] | **Approved by**: [Architect]
```

---

## References

- [CLAUDE.md](../../CLAUDE.md) — Project rules
- [docs/guides/onboarding-claude-code.md](onboarding-claude-code.md) — Team onboarding
- [docs/guides/validation.md](validation.md) — Validation commands
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Git workflow
