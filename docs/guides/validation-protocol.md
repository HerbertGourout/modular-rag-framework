# Validation Protocol & CI Alignment

This document is the canonical reference for validating this project locally and in CI:
installation, the four validation tiers, CI/CD alignment, common workflows, exit codes, and
troubleshooting. It absorbs `docs/guides/validation.md`, which duplicated ~70% of this content
under a different structure — see the note at the bottom for what changed.

**Status:** V1 complete
**Merged and corrected:** 2026-08-06 (documentation audit, `docs/archive/documentation-audit-2026-08.md`)

---

## 00 — Installation & Setup

```bash
# Clone repository
git clone https://github.com/HerbertGourout/modular-rag-framework.git
cd modular-rag-framework

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # Linux/macOS

# Install minimal (core only)
pip install -e "."

# Install V1 stack (recommended)
pip install -e ".[v1,dev]"

# Install everything (v1 + v4 + v5 + langgraph + dev — no "v3", removed in Lot 17)
pip install -e ".[all]"
```

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

**Blocks on:** syntax errors (E9xx), undefined names (F8xx), import order violations (I001-I002).
**Allows:** type hint issues (checked but not blocking below the mypy baseline), complex logic
problems (caught by tests, not lint).

### Tier 2: Full Check (~2-5 minutes)
**When:** Before merge, pre-commit to main
**What:** Compilation, hexagonal layering audit, ratcheted mypy, runnable-manifest check, unit
tests, contract tests
**Tools:** `python -m compileall`, `scripts/check_layering.py`, `mypy`, `pytest`

```bash
./scripts/check.sh full
# OR manually:
python -m compileall -q src/modular_rag
python scripts/check_layering.py --strict
mypy src/modular_rag/ --no-error-summary   # compare count against .claude/mypy-baseline.txt
pytest tests/unit/ -v
pytest tests/contract/ -v
```

**Blocks on:** failed unit tests, failed contract tests, syntax/import/layering errors, mypy
error count exceeding `.claude/mypy-baseline.txt`'s ratchet.
**Allows:** mypy errors already present in the baseline (the baseline only ratchets down, never
up — see the file's own header comment).

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

**Blocks on:** failed integration tests, Qdrant connection errors.
**Skips gracefully if:** Qdrant unavailable.

### Tier 4: E2E Check (~2-5 minutes)
**When:** Full pipeline validation
**What:** End-to-end tests
**Requires:** Qdrant + LLM API key

```bash
export OPENAI_API_KEY=sk-...
docker run -p 6333:6333 qdrant/qdrant &
./scripts/check.sh e2e
# OR
pytest tests/e2e/ -v -m e2e
```

**Blocks on:** failed E2E tests, missing LLM API key, Qdrant unavailable.

### Tier All: Comprehensive (~10 minutes)
**When:** Before major release, milestone verification

```bash
./scripts/check.sh all
```

**Runs:** Tier 1 → Tier 2 → Tier 3 → Tier 4.

---

## 02 — Validation Mapping

| Stage | Command | Scope | Time | Blocks | Requires |
|-------|---------|-------|------|--------|----------|
| **Lint** | `ruff check src/modular_rag tests/` | Syntax, imports, undefined | ~15s | E,F,I errors | Nothing |
| **Compile** | `python -m compileall src/modular_rag` | Byte-compilation | ~5s | Syntax errors | Nothing |
| **Layering** | `python scripts/check_layering.py --strict` | Hexagonal import boundaries | ~5s | Any non-baselined violation | Nothing |
| **Type** | `mypy src/modular_rag/` | Type hints, ratcheted | ~30s | Count above baseline | Python 3.11+ |
| **Unit** | `pytest tests/unit/ -v` | No ext services | ~5-7s | Failed tests | pytest |
| **Contract** | `pytest tests/contract/ -v` | Protocol conformance | ~1s | Failed tests | pytest |
| **Integration** | `pytest tests/integration/ -m integration -v` | With Qdrant | ~1-2m | Failed tests | Qdrant |
| **E2E** | `pytest tests/e2e/ -m e2e -v` | Full pipeline | ~2-5m | Failed tests | Qdrant + LLM key |

---

## 03 — CI/CD Alignment

### Local: developer machine
```bash
./scripts/check.sh quick    # Fast feedback loop
./scripts/check.sh full     # Pre-merge validation
./scripts/check.sh all      # Pre-release
```

### CI/CD: `.github/workflows/ci.yml` — the real, current 7-job pipeline

All 7 jobs below are wired into the real workflow today (not illustrative). Corrected here — an
earlier version of this document only listed 3 of them and predated Lots 15-18.

| Job | What it runs | Needs |
|---|---|---|
| `lint` | ruff, compileall, layering audit, ratcheted mypy, runnable-manifest check | — |
| `test-unit` | `pytest tests/unit/` — installs `.[v1,langgraph,dev]` (`langgraph` is required here, not optional: `tests/unit/adapters/llms/test_langgraph_engine.py` really calls the LangGraph adapter) | `lint`... no, runs independently |
| `test-contract` | `pytest tests/contract/` | — |
| `coverage` | Both suites with `--cov`, uploads `coverage.xml` | `test-unit`, `test-contract` |
| `build-and-smoke-test` | Builds a wheel, installs it into a fresh venv, runs `mrag version` | `lint`, `test-unit`, `test-contract` |
| `supply-chain` | `pip-audit`, `scripts/check_licenses.py`, generates a CycloneDX SBOM | — |
| `container-build` | Builds the `Dockerfile`, runs it, polls `/health` | `lint`, `test-unit`, `test-contract` |

`integration`/`e2e` are **not** wired into CI — both need a live Qdrant (and, for e2e, a real
LLM key), which the CI runners don't provision. Run them locally instead (Tier 3/4 above).

### Alignment checklist
- ✅ Local `quick` ↔ CI `lint` (same commands)
- ✅ Local `full` ↔ CI `lint` + `test-unit` + `test-contract` (same commands)
- ✅ Local `integration`/`e2e` ↔ not run in CI, run locally against real services
- ✅ Same pytest markers: `unit`, `contract`, `integration`, `e2e`

---

## 04 — Validation Scenarios

### Scenario A: Daily Development
```bash
./scripts/check.sh quick        # After each edit, ~30s
./scripts/check.sh full         # Before committing, ~2-5m
git push origin feature/xxx     # If tests pass
```

### Scenario B: Pre-Merge (MR/PR)
```bash
git push origin feature/xxx
./scripts/check.sh full         # CI runs this
./scripts/check.sh integration  # Optional, with services
# All green → merge to main
```

### Scenario C: Pre-Release
```bash
./scripts/check.sh all          # All tiers
python examples/simple_qa/main.py ask "Question?"   # Manual sanity check
git tag v0.1.0
git push origin v0.1.0
```

### Scenario D: Debugging Failures
```bash
./scripts/check.sh quick                              # 1. Identify ruff/layering violations
pytest tests/unit/ -v --tb=short                       # 2. Check unit tests
pytest tests/contract/ -v --tb=short -k "failing_protocol"  # 3. Check contract compliance
./scripts/check.sh integration                         # 4. Check integration, if Qdrant matters
```

---

## 05 — Exit Codes & Signals

| Code | Meaning | Action |
|------|---------|--------|
| 0 | All validations passed | ✅ Safe to proceed |
| 1 | Validation failed | ❌ Fix errors before merge |
| N/A | Service unavailable (e.g., Qdrant) | ⚠️ Continue with skipped tests |

```bash
$ ./scripts/check.sh integration
⚠ Qdrant not available on localhost:6333 — skipping integration tests
# Exit code: 0 (not treated as failure — Qdrant is optional for local development)
```

CLI commands (`mrag ask`/`mrag ingest`) have their own typed exit codes since Lot 16a: `2`
configuration error, `3` security/policy denial, `4` other framework error, `1` unexpected —
see `src/modular_rag/cli/__init__.py`.

---

## 06 — Performance Targets

| Tier | Target |
|------|--------|
| Quick | ~30s |
| Full | ~2-5m |
| Integration | ~1-2m |
| E2E | ~2-5m |
| All | ~10m |

*(Figures are targets, not continuously measured — treat as budgets to notice a regression
against, not a guaranteed SLA.)*

---

## 07 — Test Markers (pytest)

```python
# Unit tests (no external services)
def test_chunker_splits_correctly():
    ...

# Contract tests (Protocol conformance)
def test_chunker_conforms_to_protocol():
    ...

# Integration tests (require Qdrant)
@pytest.mark.integration
def test_vector_store_persistence():
    ...

# E2E tests (require Qdrant + LLM API key)
@pytest.mark.e2e
def test_full_pipeline():
    ...
```

```bash
pytest tests/ -m "not integration"   # Skip integration
pytest tests/ -m "e2e"               # Only E2E
```

---

## 08 — CLI & API (Development)

### CLI commands
```bash
mrag ingest ./my_docs --manifest manifests/presets/local-hybrid-rag.yaml
mrag ask "What is RAG?" --manifest manifests/presets/local-hybrid-rag.yaml
mrag ask "What is RAG?" --manifest manifests/presets/local-hybrid-rag.yaml --tenant-id acme
mrag validate manifests/presets/local-hybrid-rag.yaml
```

### REST API

`create_app()` requires a `manifest_path` argument — bare `uvicorn modular_rag.api:create_app
--factory` does **not** work. Use the one-line `server.py` wrapper pattern (real, current
example: [`docker/server.py`](../../docker/server.py)):

```bash
MRAG_MANIFEST_PATH=manifests/presets/local-hybrid-rag.yaml \
uvicorn server:app --app-dir docker --reload --host 0.0.0.0 --port 8000
```

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is hybrid retrieval?"}'
```

---

## 09 — Examples

```bash
export OPENAI_API_KEY=sk-...
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
python examples/simple_qa/main.py ask "What is RAG?"
```

```python
from modular_rag.app.bootstrap import load_pipeline

pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
answer = pipeline.answer("Explain Modular RAG")
print(answer.text)
for citation in answer.citations:
    print(f"  - {citation.source} (score: {citation.score})")
```

---

## 10 — Common Workflows

### Add a new chunker
```bash
cat tests/contract/test_chunker_conformance.py   # 1. Read the Protocol conformance test
vim src/modular_rag/ingestion/chunkers/my_chunker.py   # 2. Implement
vim tests/unit/ingestion/chunkers/test_my_chunker.py   # 3. Add unit tests
./scripts/check.sh full                                # 4. Validate
vim manifests/presets/local-hybrid-rag.yaml             # 5. Register in the manifest
```

### Modify a core Protocol
```bash
cat .claude/rules/contracts.md          # 1. Read the rules — this is an "ask"-tier path
vim src/modular_rag/contracts/chunking.py         # 2. Update the Protocol
grep -rl "class.*Chunker.*:" src/                 # 3. Find every implementation to update
vim tests/contract/test_chunker_conformance.py    # 4. Update conformance tests
./scripts/check.sh full                           # 5. Run full validation
```

### Fix a security issue
```bash
cat src/modular_rag/security/CLAUDE.md   # 1. Read the rules
vim tests/unit/security/test_basic_guard.py   # 2. Add a regression test
vim src/modular_rag/security/filters/basic_guard.py   # 3. Implement the fix
./scripts/check.sh all                                 # 4. Verify all paths
```

---

## 11 — Troubleshooting

### "Quick check fails with import errors" / "Import errors after changes"
```bash
pip install -e ".[v1,dev]"
# Or force a rebuild:
pip uninstall -y modular-rag && pip install -e ".[v1,dev]"
```

### "Full check passes locally but fails in CI"
1. Python version mismatch → check `python --version` (CI runs 3.12)
2. Package/extras not installed → `pip install -e ".[v1,langgraph,dev]"` (note: `langgraph` is
   required for the full unit suite, not just `v1,dev` — see §03's `test-unit` row)
3. Cached dependencies → `pip install --force-reinstall -e ".[v1,dev]"`

### "Qdrant not available"
```bash
docker run -p 6333:6333 qdrant/qdrant
# Or skip integration tests:
pytest tests/ -m "not integration"
```

### "LLM API key not found"
```bash
export OPENAI_API_KEY=sk-...        # or:
export ANTHROPIC_API_KEY=sk-ant-...
echo $OPENAI_API_KEY
```
Note: the working variable is the SDK's own standard name (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`),
**not** `MRAG_OPENAI_API_KEY`/`MRAG_ANTHROPIC_API_KEY` — `app/settings.py`'s `Settings` class
once declared those `MRAG_`-prefixed names but nothing in the real pipeline-wiring path ever
constructed a `Settings()` (found in Lot 16c, `docs/refactoring/lot-16c-deployment-runbooks.md`);
the file was deleted outright in Étape 8 of the ADR-0007 stabilization pass.

### "Type hints not working" / mypy questions
```bash
mypy src/modular_rag/ --no-error-summary
```
Type checking is ratcheted, not fully blocking — compare the error count against
`.claude/mypy-baseline.txt`; only a count *increase* fails CI.

---

## References

- **Development guide:** [docs/guides/getting-started.md](./getting-started.md)
- **Architecture:** [docs/architecture/overview.md](../architecture/overview.md)
- **Testing strategy:** [.claude/rules/tests.md](../../.claude/rules/tests.md)
- **Claude Code customization:** [.claude/settings.json](../../.claude/settings.json)
- **Quick reference:** [CLAUDE.md block 04](../../CLAUDE.md#04--development-commands)

---

*This document absorbed `docs/guides/validation.md` on 2026-08-06 (documentation audit) — the
two files had ~70% overlapping content (CI/CD tables, validation-strategy walkthroughs,
troubleshooting) under different structures. `validation.md` now redirects here.*
