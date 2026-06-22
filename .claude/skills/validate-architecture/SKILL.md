---
name: validate-architecture
description: Comprehensive validation workflow for verifying hexagonal layering, imports, and design patterns
---

# Validate Architecture Skill

_Originally authored as a workflow for `architecture-reviewer`, invoked as `/validate-architecture`._


Comprehensive workflow for validating architecture compliance, import rules, and design patterns.

## When to Use

- Before committing new features
- When adding components to multiple layers
- When refactoring or restructuring code
- When investigating import errors
- Before creating merge request

## Validation Checklist

### 1. Layering Compliance (10 min)

**Verify dependency flow:**

```bash
# Check imports follow one direction
./scripts/check.sh quick  # Catches E, F, I ruff errors
```

**Manual verification:**

```python
# File: src/modular_rag/retrieval/hybrid_retriever.py

# ✅ ALLOWED imports
from modular_rag.contracts.retrieval import RetrieverProtocol  # Contracts
from modular_rag.core.models import SearchResult  # Core
from modular_rag.core.trace import Trace, TraceStep  # Core

# ❌ NOT ALLOWED imports
from modular_rag.generation.openai_generator import OpenAIGenerator  # Cross-domain!
from modular_rag.ingestion.chunkers import FixedChunker  # Cross-domain!
from modular_rag.security.filters import PromptInjectionFilter  # Cross-domain!
```

**Decision tree:**
- Does import come from `contracts/` or `core/`? → ✅ Allowed
- Does import come from `adapters/`? → ✅ Allowed (for adapter configs)
- Does import come from same domain? → ✅ Allowed
- Does import come from different domain? → ❌ NOT allowed

### 2. Import Validation (10 min)

**Check for cross-domain imports:**

```python
# Run grep search
grep -r "from modular_rag\\.generation" src/modular_rag/retrieval/
grep -r "from modular_rag\\.ingestion" src/modular_rag/security/
grep -r "from modular_rag\\.retrieval" src/modular_rag/generation/

# If any results → Architecture violation
```

**Check for lazy imports on heavy libraries:**

```python
# ✅ GOOD: Lazy import (inside function)
def retrieve(self, query: str):
    from rank_bm25 import BM25Okapi  # Imported here
    index = BM25Okapi(...)

# ❌ BAD: Module-level import
from rank_bm25 import BM25Okapi  # At top of file
class BM25Retriever:
    def retrieve(self, query: str):
        index = BM25Okapi(...)
```

**Required lazy imports for:**
- `qdrant-client`
- `rank-bm25`
- `sentence-transformers`
- `openai`
- `anthropic`
- `pydantic`
- `fitz` (pdf parsing)

### 3. Protocol Compliance (10 min)

**Checklist for each new class:**

```python
# ✅ Implement correct Protocol
class MyRetriever(RetrieverProtocol):  # Inherits from Protocol
    
    # ✅ All required methods implemented
    def retrieve(self, query: str, k: int = 10) -> list[SearchResult]:
        ...
    
    # ✅ Type hints on all parameters and returns
    def retrieve(self, query: str, k: int = 10) -> list[SearchResult]:
        ...
    
    # ✅ TraceStep emitted for observability
    step = TraceStep(component="MyRetriever", method="retrieve")
    try:
        results = [...]
        step.metadata = {"count": len(results)}
        return results
    finally:
        Trace.add_step(step)
```

**Verify Protocol:**
```bash
# Check Protocol is inherited
grep -n "class.*Protocol" src/modular_rag/contracts/retrieval.py

# Verify implementation
python3 -c "
from modular_rag.retrieval.my_retriever import MyRetriever
from modular_rag.contracts.retrieval import RetrieverProtocol
assert issubclass(MyRetriever, RetrieverProtocol)
print('✅ Protocol implemented correctly')
"
```

### 4. Dependency Injection Pattern (10 min)

**Verify wiring through registry:**

```python
# ✅ GOOD: Registered in registry
# src/modular_rag/orchestration/registry.py
def _create_my_retriever(config: dict) -> RetrieverProtocol:
    return MyRetriever(config)

BUILT_IN_RETRIEVERS = {
    "my_retriever": _create_my_retriever,
}

# ✅ GOOD: Wired through YAML manifest
# manifests/presets/my-rag.yaml
retrieval:
  retrievers:
    - type: my_retriever
      config_param: value

# ❌ BAD: Direct Python instantiation
# src/modular_rag/app/bootstrap.py
retriever = MyRetriever(config)  # Don't do this!
```

**Verification:**
```bash
# Search for direct instantiation
grep -r "MyRetriever()" src/modular_rag/

# If any results (outside tests) → Architecture violation
```

### 5. Adapter Isolation (10 min)

**For adapters, verify:**

```python
# File: src/modular_rag/adapters/vectorstores/my_store.py

# ✅ ALLOWED imports
from modular_rag.contracts.indexing import VectorStoreProtocol  # Protocol
from modular_rag.core.models import Document  # Core
from external_lib import ExternalStore  # External library (lazy)

# ❌ NOT ALLOWED imports
from modular_rag.retrieval import VectorRetriever  # Domain module!
from modular_rag.ingestion import FixedChunker  # Domain module!
```

**Checklist:**
- [ ] Adapters only import `contracts/` + `core/`
- [ ] Adapters never import domain modules
- [ ] Heavy dependencies lazy-imported
- [ ] Factory method in registry

### 6. File Organization (5 min)

**Verify file structure:**

```
✅ GOOD:
src/modular_rag/retrieval/
├── __init__.py
├── vector_retriever.py
├── bm25_retriever.py
└── hybrid_retriever.py

❌ BAD:
src/modular_rag/
├── retrieval_vector_retriever.py  # Wrong location
├── my_utils.py  # Ambiguous
└── temporary_file.py  # Temporary files
```

### 7. Test Mirror (10 min)

**Verify test structure mirrors code:**

```
✅ GOOD:
src/modular_rag/retrieval/vector_retriever.py
tests/unit/retrieval/test_vector_retriever.py
tests/contract/test_vector_retriever_conformance.py

❌ BAD:
src/modular_rag/retrieval/vector_retriever.py
tests/my_test.py  # Wrong location
tests/test_retrieval_all.py  # Wrong naming
```

### 8. Run Full Validation (5 min)

**Execute validation commands:**

```bash
# Quick syntax check (30s)
./scripts/check.sh quick

# Full check with tests (2-5 min)
./scripts/check.sh full

# Individual checks
pytest tests/unit/ -v
pytest tests/contract/ -v
ruff check src/modular_rag/ --select E,F,I
```

## Common Architecture Violations

### Violation 1: Cross-Domain Import

**Problem:**
```python
# src/modular_rag/retrieval/hybrid_retriever.py
from modular_rag.generation import OpenAIGenerator  # ❌ Cross-domain!
```

**Solution:**
```python
# Use Protocol instead
from modular_rag.contracts.generation import GeneratorProtocol

class HybridRetriever:
    def __init__(self, generator: GeneratorProtocol):
        self.generator = generator  # Injected
```

### Violation 2: Missing Lazy Import

**Problem:**
```python
# Module-level import of heavy library
from rank_bm25 import BM25Okapi

class BM25Retriever:
    def retrieve(self, query: str):
        index = BM25Okapi(...)
```

**Solution:**
```python
class BM25Retriever:
    def retrieve(self, query: str):
        from rank_bm25 import BM25Okapi  # Lazy import
        index = BM25Okapi(...)
```

### Violation 3: Direct Python Wiring

**Problem:**
```python
# src/modular_rag/app/bootstrap.py
retriever = VectorRetriever(embedder_config)  # ❌ Direct instantiation
generator = OpenAIGenerator(model_config)  # ❌ Direct instantiation
```

**Solution:**
```python
# Use registry + manifest
registry = ComponentRegistry()
config = load_manifest("manifests/presets/local-rag.yaml")
retriever = registry.create("retriever", config["retrieval"])
generator = registry.create("generator", config["generation"])
```

### Violation 4: Missing TraceStep

**Problem:**
```python
class MyRetriever(RetrieverProtocol):
    def retrieve(self, query: str, k: int = 10):
        results = [...]
        return results  # ❌ No tracing!
```

**Solution:**
```python
class MyRetriever(RetrieverProtocol):
    def retrieve(self, query: str, k: int = 10):
        step = TraceStep(component="MyRetriever", method="retrieve")
        try:
            results = [...]
            step.metadata = {"count": len(results)}
            return results
        finally:
            Trace.add_step(step)
```

## Validation Report Template

**Create after validation:**

```markdown
# Architecture Validation Report

**Date:** 2026-06-20
**Reviewer:** @dev
**PR:** #42 "Add BM25Retriever"

## Validation Results

### Layering Compliance
- [x] All imports follow one-directional flow
- [x] No cross-domain imports detected
- [x] Adapter isolation maintained

### Protocol Compliance
- [x] RetrieverProtocol fully implemented
- [x] All methods have type hints
- [x] TraceStep emission complete

### Testing
- [x] Unit tests: 42 tests, 92% coverage
- [x] Contract tests: 3 tests, passing
- [x] Integration tests: 2 tests, passing

### Performance
- [x] Retrieval latency: <100ms
- [x] Memory overhead: <10MB
- [x] No performance regressions

## Status
✅ **PASSED** - Ready for merge

## Recommendations
None
```

## Success Criteria

✅ All imports follow hexagonal pattern
✅ No cross-domain imports detected
✅ Lazy imports on external libraries
✅ Protocol implementations verified
✅ Registry + YAML wiring confirmed
✅ TraceStep emission complete
✅ Test structure mirrors code
✅ All validation checks passing

## Time Estimate

**Total:** 10-15 minutes for small changes, up to 30 min for large refactorings
