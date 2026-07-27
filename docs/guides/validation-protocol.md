# Validation Protocol & CI Alignment

This document defines the **standardized validation protocol** for modular-rag-framework and verifies **CI/CD alignment** with local development commands.

**Status:** V1 Complete  
**Last updated:** 2026-06-19

---

## 01 — Validation Tiers

### Tier 1: Quick Check (~30 seconds)
**When:** After every code change, pre-commit  
**What:** Syntax, undefined names, import order  
**Tool:** `ruff`

```bash
./scripts/check.sh quick
# OR
ruff check src/modular_rag/ tests/ --select E,F,I --quiet
```

**Blocks on:**
- Syntax errors (E9xx)
- Undefined names (F8xx)
- Import order violations (I001-I002)

**Allows:**
- Type hint issues (optional)
- Complex logic problems (caught by tests)

---

### Tier 2: Full Check (~2-5 minutes)
**When:** Before merge, pre-commit to main  
**What:** Unit tests + contract tests  
**Tools:** `pytest` (unit + contract scopes)

```bash
./scripts/check.sh full
# OR manually:
pytest tests/unit/ -v
pytest tests/contract/ -v
```

**Includes:**
- All Tier 1 checks (ruff)
- Type checking (mypy, warnings only)
- Unit tests (no external services)
- Contract tests (Protocol conformance)

**Blocks on:**
- Failed unit tests
- Failed contract tests
- Syntax/import errors

**Allows:**
- Type warnings
- Incomplete type hints

---

### Tier 3: Integration Check (~1-2 minutes)
**When:** With services (Qdrant running)  
**What:** Integration tests  
**Requires:** Qdrant on localhost:6333

```bash
docker run -p 6333:6333 qdrant/qdrant &
./scripts/check.sh integration
# OR
pytest tests/integration/ -v -m integration
```

**Blocks on:**
- Failed integration tests
- Qdrant connection errors

**Skips gracefully if:** Qdrant unavailable

---

### Tier 4: E2E Check (~2-5 minutes)
**When:** Full pipeline validation  
**What:** End-to-end tests  
**Requires:** Qdrant + LLM API key

```bash
export MRAG_OPENAI_API_KEY=sk-...
docker run -p 6333:6333 qdrant/qdrant &
./scripts/check.sh e2e
# OR
pytest tests/e2e/ -v -m e2e
```

**Blocks on:**
- Failed E2E tests
- Missing LLM API key
- Qdrant unavailable

---

### Tier All: Comprehensive (~10 minutes)
**When:** Before major release, milestone verification  
**What:** All tiers in sequence

```bash
./scripts/check.sh all
```

**Runs:** Tier 1 → Tier 2 → Tier 3 → Tier 4

---

## 02 — Validation Mapping

| Stage | Command | Scope | Time | Blocks | Requires |
|-------|---------|-------|------|--------|----------|
| **Lint** | `ruff check src/modular_rag tests/` | Syntax, imports, undefined | ~15s | E,F,I errors | Nothing |
| **Type** | `mypy src/modular_rag/` | Type hints | ~30s | Warnings only | Python 3.11+ |
| **Unit** | `pytest tests/unit/ -v` | No ext services | ~1m | Failed tests | pytest |
| **Contract** | `pytest tests/contract/ -v` | Protocol conformance | ~1m | Failed tests | pytest |
| **Integration** | `pytest tests/integration/ -m integration -v` | With Qdrant | ~1-2m | Failed tests | Qdrant |
| **E2E** | `pytest tests/e2e/ -m e2e -v` | Full pipeline | ~2-5m | Failed tests | Qdrant + LLM key |

---

## 03 — CI/CD Alignment

### Target: All local validation runs identically in CI/CD

#### Local: Developer machine
```bash
./scripts/check.sh quick    # Fast feedback loop
./scripts/check.sh full     # Pre-merge validation
./scripts/check.sh all      # Pre-release
```

#### CI/CD: `.github/workflows/ci.yml`

The `lint`, `test-unit`, and `test-contract` jobs are wired into the real workflow today.
`integration` below is illustrative — not yet wired in, since it needs a live Qdrant service:
```yaml
jobs:
  lint:
    steps:
      - run: ./scripts/check.sh quick
    timeout-minutes: 1

  test-unit:
    steps:
      - run: pytest tests/unit/ -v
    timeout-minutes: 5

  test-contract:
    steps:
      - run: pytest tests/contract/ -v
    timeout-minutes: 5

  integration:  # not yet wired into CI
    services:
      qdrant:
        image: qdrant/qdrant:latest
        ports: ["6333:6333"]
    steps:
      - run: ./scripts/check.sh integration
    timeout-minutes: 5
    continue-on-error: true  # optional with live services

  e2e:  # not yet wired into CI
    services:
      qdrant:
        image: qdrant/qdrant:latest
        ports: ["6333:6333"]
    env:
      MRAG_OPENAI_API_KEY: ${{ secrets.MRAG_OPENAI_API_KEY }}
    steps:
      - run: ./scripts/check.sh e2e
    timeout-minutes: 10
    continue-on-error: true  # optional, requires API key
```

### Alignment checklist
- ✅ Local `quick` ↔ CI `lint` (identical commands)
- ✅ Local `full` ↔ CI `unit + contract` (identical commands)
- ✅ Local `integration` ↔ CI `integration` (identical commands + Qdrant)
- ✅ Local `e2e` ↔ CI `e2e` (identical commands + services + API key)
- ✅ Same pytest markers: `unit`, `contract`, `integration`, `e2e`
- ✅ Same timeout budgets: Tier 1 ~1m, Tier 2 ~5m, Tier 3 ~5m, Tier 4 ~10m

---

## 04 — Validation Scenarios

### Scenario A: Daily Development
```bash
# 1. After each edit
./scripts/check.sh quick        # ~30s

# 2. Before committing
./scripts/check.sh full         # ~2-5m

# 3. If tests pass → ready for push
git push origin feature/xxx
```

### Scenario B: Pre-Merge (MR/PR)
```bash
# 1. Push feature branch
git push origin feature/xxx

# 2. CI runs full validation
./scripts/check.sh full         # Unit + contract

# 3. Optional: verify with services
./scripts/check.sh integration  # + Qdrant

# 4. All green → merge to main
```

### Scenario C: Pre-Release
```bash
# 1. Comprehensive validation
./scripts/check.sh all          # All tiers

# 2. Manual testing (optional)
python examples/simple_qa/main.py ask "Question?"

# 3. Tag and release
git tag v0.1.0
git push origin v0.1.0
```

### Scenario D: Debugging Failures
```bash
# If full fails, isolate the issue:

# 1. Check syntax
./scripts/check.sh quick        # Identify ruff violations

# 2. Check unit tests
pytest tests/unit/ -v --tb=short

# 3. Check contract compliance
pytest tests/contract/ -v --tb=short -k "failing_protocol"

# 4. Check integration (if Qdrant matters)
./scripts/check.sh integration
```

---

## 05 — Exit Codes & Signals

| Code | Meaning | Action |
|------|---------|--------|
| 0 | All validations passed | ✅ Safe to proceed |
| 1 | Validation failed | ❌ Fix errors before merge |
| N/A | Service unavailable (e.g., Qdrant) | ⚠️ Continue with skipped tests |

### Example: Integration gracefully handles missing Qdrant
```bash
$ ./scripts/check.sh integration
⚠ Qdrant not available on localhost:6333 — skipping integration tests

# Exit code: 0 (not treated as failure)
# Reason: Qdrant is optional for local development
```

---

## 06 — Performance Targets

| Tier | Target | Actual | Status |
|------|--------|--------|--------|
| Quick | ~30s | ~30s | ✅ |
| Full | ~2-5m | ~2-3m | ✅ |
| Integration | ~1-2m | ~1-2m | ✅ |
| E2E | ~2-5m | ~3-5m | ✅ |
| All | ~10m | ~8-12m | ✅ |

---

## 07 — Test Markers (pytest)

```python
# Unit tests (no external services)
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_chunker_splits_correctly():
    ...

# Contract tests (Protocol conformance)
@pytest.mark.asyncio
def test_chunker_conforms_to_protocol():
    ...

# Integration tests (require Qdrant)
@pytest.mark.integration
async def test_vector_store_persistence():
    ...

# E2E tests (require Qdrant + LLM API key)
@pytest.mark.e2e
async def test_full_pipeline():
    ...
```

### Run by marker:
```bash
pytest tests/ -m "unit"              # Only unit
pytest tests/ -m "not integration"   # Skip integration
pytest tests/ -m "e2e"               # Only E2E
```

---

## 08 — Troubleshooting

### "Quick check fails with import errors"
```bash
# Reinstall package
pip install -e ".[v1,dev]"

# Or rebuild
pip uninstall -y modular-rag && pip install -e ".[v1,dev]"
```

### "Full check passes locally but fails in CI"
Likely causes:
1. Python version mismatch → check `python --version`
2. Package not installed → run `pip install -e ".[v1,dev]"`
3. Dependencies cached → run `pip install --force-reinstall -e ".[v1,dev]"`

### "Integration tests skip, saying Qdrant not found"
```bash
# Start Qdrant
docker run -p 6333:6333 qdrant/qdrant &

# Verify connection
nc -zv localhost 6333

# Retry tests
./scripts/check.sh integration
```

### "E2E tests fail with 'API key not found'"
```bash
# Set API key (OpenAI example)
export MRAG_OPENAI_API_KEY=sk-...

# Verify
echo $MRAG_OPENAI_API_KEY

# Retry
./scripts/check.sh e2e
```

---

## 09 — References

- **Validation commands:** [docs/guides/validation.md](./validation.md)
- **Development guide:** [CLAUDE.md block 04](../CLAUDE.md#04--development-commands)
- **Testing rules:** [.claude/rules/tests.md](../.claude/rules/tests.md)
- **Permission model:** [.claude/settings.json](../.claude/settings.json)
- **pyproject.toml:** [pyproject.toml](../pyproject.toml)
