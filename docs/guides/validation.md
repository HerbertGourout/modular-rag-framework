# Command Inventory & Validation Strategy

This document inventories all development, validation, and deployment commands for the modular-rag-framework.

**Last updated:** 2026-06-19  
**Scope:** V1 (Core RAG)

---

## 01 — Installation & Setup

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

# Install all versions + dev
pip install -e ".[all]"
```

---

## 02 — Quick Checks (< 1 minute) — Use daily, pre-commit

### Script-based (recommended)
```bash
./scripts/check.sh quick    # Ruff syntax + imports

./scripts/check.sh full     # Quick + unit + contract tests
```

### Manual commands
```bash
# Syntax check, import order, undefined names
ruff check src/modular_rag/ tests/ --select E,F,I

# Auto-fix common issues
ruff check src/modular_rag/ tests/ --select E,F,I --fix

# Type hints (optional, not blocking)
mypy src/modular_rag/
```

---

## 03 — Unit Tests — No external services required

```bash
# All unit tests
pytest tests/unit/ -v

# Single test file
pytest tests/unit/ingestion/chunkers/test_fixed.py -v

# Single test case
pytest tests/unit/ingestion/chunkers/test_fixed.py::test_short_text_single_chunk -v

# With coverage
pytest tests/unit/ --cov=src/modular_rag/ --cov-report=html
```

---

## 04 — Contract Tests — Protocol conformance (no external services)

Every Protocol in `src/modular_rag/contracts/` must have a conformance test:

```bash
# All contract tests
pytest tests/contract/ -v

# Specific protocol (e.g., chunkers)
pytest tests/contract/test_chunker_conformance.py -v
```

---

## 05 — Integration Tests — With Qdrant (requires service)

### Prerequisites
```bash
# Start Qdrant on localhost:6333
docker run -p 6333:6333 qdrant/qdrant
# or: brew install qdrant (macOS)
```

### Run tests
```bash
# Integration tests only
pytest tests/integration/ -v -m integration

# All tests except integration
pytest tests/ -v -m "not integration"
```

---

## 06 — End-to-End Tests — Full pipeline (requires Qdrant + LLM API key)

### Prerequisites
```bash
# 1. Start Qdrant
docker run -p 6333:6333 qdrant/qdrant &

# 2. Set LLM API key (OpenAI or Anthropic)
export MRAG_OPENAI_API_KEY=sk-...       # Linux/macOS
$env:MRAG_OPENAI_API_KEY="sk-..."       # Windows PowerShell

# Or use Anthropic
export MRAG_ANTHROPIC_API_KEY=sk-ant-...
```

### Run tests
```bash
# E2E tests only
pytest tests/e2e/ -v -m e2e

# Only fast tests (skip e2e + integration)
pytest tests/ -v -m "not (e2e or integration)"
```

---

## 07 — CLI & API (Development)

### CLI Commands
```bash
# Ingest documents
mrag ingest ./my_docs \
  --manifest manifests/presets/local-hybrid-rag.yaml

# Ask question
mrag ask "What is RAG?" \
  --manifest manifests/presets/local-hybrid-rag.yaml

# With Qdrant backend
QDRANT_URL=http://localhost:6333 mrag ask "Question?"
```

### REST API
```bash
# Start development server (hot-reload)
uvicorn modular_rag.api:create_app --factory --reload

# Or production-like
gunicorn modular_rag.api:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Test endpoints
curl http://localhost:8000/health
curl -X POST http://localhost:8000/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is hybrid retrieval?"}'
```

---

## 08 — Examples (End-to-end demonstrations)

### Simple QA Example
```bash
# Set API key
export MRAG_OPENAI_API_KEY=sk-...

# Ingest documents
python examples/simple_qa/main.py ingest examples/simple_qa/docs/

# Ask question
python examples/simple_qa/main.py ask "What is RAG?"

# View Python integration
cat examples/simple_qa/main.py
```

### Using Framework Directly
```python
from modular_rag.app.bootstrap import load_pipeline

# Load manifest
pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")

# Ask question
answer = pipeline.answer("Explain Modular RAG")
print(answer.text)

# View citations
for citation in answer.citations:
    print(f"  - {citation.source} (score: {citation.score})")
```

---

## 09 — Validation Strategies

### Strategy 1: Daily Development
```bash
# After each change
./scripts/check.sh quick        # Syntax & imports (~30s)

# Before committing
./scripts/check.sh full         # Unit + contracts (~2-5m)
```

### Strategy 2: Pre-Merge (MR/PR)
```bash
# Requires passing:
./scripts/check.sh full         # Unit + contracts

# Optional with Qdrant:
./scripts/check.sh integration  # + Integration tests
```

### Strategy 3: Pre-Release / CI
```bash
# Full comprehensive validation
./scripts/check.sh all          # All scopes (~10m)

# Breakdown:
#   Step 1: Syntax + imports
#   Step 2: Type hints (warning only)
#   Step 3: Unit tests
#   Step 4: Contract tests
#   Step 5: Integration (if Qdrant available)
#   Step 6: E2E (if LLM key available)
```

---

## 10 — Common Workflows

### Add a New Chunker
```bash
# 1. Write Protocol conformance test
cat tests/contract/test_chunker_conformance.py

# 2. Implement chunker
vim src/modular_rag/ingestion/chunkers/my_chunker.py

# 3. Add unit tests
vim tests/unit/ingestion/chunkers/test_my_chunker.py

# 4. Validate
./scripts/check.sh quick    # Quick syntax check
./scripts/check.sh full     # Full test suite

# 5. Register in manifest
vim manifests/presets/local-hybrid-rag.yaml  # Add chunker config
```

### Modify Core Protocol
```bash
# 1. Read rules
cat .claude/rules/contracts.md

# 2. Understand impact (ask Claude!)
# This is a RESTRICTED path — ask before edit

# 3. Update Protocol
vim src/modular_rag/contracts/chunking.py

# 4. Update all implementations
grep -r "class.*Chunker.*:" src/ | xargs vim

# 5. Update conformance tests
vim tests/contract/test_chunker_conformance.py

# 6. Run full validation
./scripts/check.sh full
```

### Fix Security Issue
```bash
# 1. Read rules
cat src/modular_rag/security/CLAUDE.md

# 2. Add test case
vim tests/unit/security/test_filters.py

# 3. Implement fix
vim src/modular_rag/security/filters/prompt_injection.py

# 4. Verify all paths (integration + e2e)
./scripts/check.sh all
```

---

## 11 — CI/CD Alignment

| Stage | Command | Timeout | Requires |
|-------|---------|---------|----------|
| **Lint** | `ruff check src/ tests/` | 30s | Nothing |
| **Unit** | `pytest tests/unit/` | 2m | Nothing |
| **Contract** | `pytest tests/contract/` | 2m | Nothing |
| **Integration** | `pytest tests/integration/ -m integration` | 3m | Qdrant |
| **E2E** | `pytest tests/e2e/ -m e2e` | 5m | Qdrant + LLM key |

### .gitlab-ci.yml alignment
```yaml
stages:
  - lint
  - test
  - integration

lint:
  script: ruff check src/ tests/ --select E,F,I

test:unit:
  script: pytest tests/unit/ -v

test:contract:
  script: pytest tests/contract/ -v

integration:
  script: pytest tests/integration/ -m integration -v
  services:
    - qdrant:latest
```

---

## 12 — Troubleshooting

### "Qdrant not available"
```bash
# Start locally
docker run -p 6333:6333 qdrant/qdrant

# Or skip integration tests
pytest tests/ -m "not integration"
```

### "LLM API key not found"
```bash
# OpenAI
export MRAG_OPENAI_API_KEY=sk-...

# Or Anthropic
export MRAG_ANTHROPIC_API_KEY=sk-ant-...

# Check
echo $MRAG_OPENAI_API_KEY
```

### "Import errors after changes"
```bash
# Reinstall in dev mode
pip install -e ".[v1,dev]"

# Or rebuild
pip uninstall -y modular-rag && pip install -e ".[v1,dev]"
```

### "Type hints not working"
```bash
# Type checking is optional (not blocking)
# But run mypy to validate
mypy src/modular_rag/ --no-error-summary
```

---

## References

- **Development guide:** [docs/guides/getting-started.md](../docs/guides/getting-started.md)
- **Architecture:** [docs/architecture/overview.md](../docs/architecture/overview.md)
- **Testing strategy:** [.claude/rules/tests.md](../.claude/rules/tests.md)
- **Claude Code customization:** [.claude/settings.json](../.claude/settings.json)
- **Quick reference:** [CLAUDE.md block 04](../CLAUDE.md#04--development-commands)
