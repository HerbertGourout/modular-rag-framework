---
name: add-retriever
description: Step-by-step workflow for implementing a new retriever following RetrieverProtocol
---

# Add Retriever Skill

## Parameters (advisory — not schema-validated by Claude Code)

Claude Code skills don't support typed/validated parameters in frontmatter; describe these to the agent in your invocation prompt instead:

- `retriever_type` (enum, required) — one of: ['vector', 'bm25', 'hybrid', 'semantic', 'graph']
- `retriever_name` (string, required) — pattern: `^[A-Z][a-zA-Z0-9]*Retriever$`
- `external_library` (string, optional) — Optional external library dependency (e.g., qdrant-client)

_Originally authored as a workflow for `retrieval-specialist`, invoked as `/add-retriever`._


Guided workflow for implementing a new retriever component following RetrieverProtocol.

## When to Use

- Implementing a new retrieval method (vector, BM25, hybrid)
- Integrating external retrieval systems
- Optimizing retrieval for specific domains
- Adding specialized retrievers (graph-based, semantic)

## Workflow Steps

### 1. Verify Protocol Compliance (5 min)

**Actions:**
- Open `src/modular_rag/contracts/retrieval.py`
- Review `RetrieverProtocol` interface
- Identify required methods:
  - `retrieve(query: str, k: int, **kwargs) → list[SearchResult]`
  - `embed_query(query: str) → list[float]` (if applicable)
  - All methods must emit `TraceStep`

**Decision Point:**
- Does your implementation fit `RetrieverProtocol`?
  - YES → Continue to step 2
  - NO → Contact architecture-reviewer

### 2. Setup Implementation Directory (5 min)

**Structure:**
```
src/modular_rag/retrieval/
├── __init__.py
├── vector_retriever.py      (existing)
├── bm25_retriever.py        (existing)
└── {retriever_name.py}      (NEW)
```

**Create file:**
```python
# src/modular_rag/retrieval/my_retriever.py

from modular_rag.contracts.retrieval import RetrieverProtocol, SearchResult
from modular_rag.core.trace import Trace, TraceStep
from modular_rag.core.models import RagConfig
from typing import List

class {RetrieverName}(RetrieverProtocol):
    """
    {{Description of retriever}}
    
    External dependency: {{external_library}} (lazy imported)
    """
    
    def __init__(self, config: RagConfig, **kwargs):
        self.config = config
        # Lazy import heavy dependencies
        
    async def retrieve(
        self, 
        query: str, 
        k: int = 10, 
        **kwargs
    ) -> List[SearchResult]:
        """Retrieve documents."""
        step = TraceStep(
            component=self.__class__.__name__,
            method="retrieve"
        )
        
        try:
            # Implementation here
            results = [...]
            step.metadata["results_count"] = len(results)
            return results
        except Exception as e:
            step.status = "error"
            step.error = str(e)
            raise
        finally:
            Trace.add_step(step)
```

### 3. Implement Core Methods (20-30 min)

**Pattern for retrieve():**
```python
async def retrieve(self, query: str, k: int = 10, **kwargs):
    step = TraceStep(component=self.__class__.__name__, method="retrieve")
    
    try:
        # 1. Validate input
        assert query, "Query cannot be empty"
        assert k > 0, "k must be > 0"
        
        # 2. Process query (e.g., embed, tokenize)
        processed_query = self._process_query(query)
        
        # 3. Search (from external service/index)
        raw_results = await self._search(processed_query, k)
        
        # 4. Transform to SearchResult
        results = [SearchResult(
            doc_id=r.id,
            text=r.text,
            score=r.score,
            metadata=r.metadata
        ) for r in raw_results]
        
        # 5. Track metrics
        step.metadata = {
            "query_length": len(query),
            "results_count": len(results),
            "top_score": results[0].score if results else 0
        }
        
        return results
        
    except Exception as e:
        step.status = "error"
        step.error = str(e)
        raise
    finally:
        Trace.add_step(step)
```

**Lazy imports pattern:**
```python
async def retrieve(self, query: str, k: int = 10, **kwargs):
    # Import heavy library inside method, not at module level
    from external_lib import ExternalRetriever
    
    retriever = ExternalRetriever(self.config.get("api_key"))
    return retriever.search(query, k)
```

### 4. Create Unit Tests (15-20 min)

**File:** `tests/unit/retrieval/test_my_retriever.py`

```python
import pytest
from modular_rag.retrieval.my_retriever import {RetrieverName}
from modular_rag.core.models import RagConfig

class Test{RetrieverName}:
    
    @pytest.fixture
    def retriever(self):
        config = RagConfig(...)
        return {RetrieverName}(config)
    
    @pytest.fixture
    def sample_query(self):
        return "What is RAG?"
    
    # Test successful retrieval
    def test_retrieve_success(self, retriever, sample_query):
        results = retriever.retrieve(sample_query, k=10)
        assert len(results) <= 10
        assert all(hasattr(r, 'doc_id') for r in results)
    
    # Test edge cases
    def test_empty_query(self, retriever):
        with pytest.raises(AssertionError):
            retriever.retrieve("", k=10)
    
    def test_large_k(self, retriever, sample_query):
        results = retriever.retrieve(sample_query, k=1000)
        assert len(results) <= 1000
    
    # Test trace emission
    def test_trace_emission(self, retriever, sample_query):
        # Ensure TraceStep is emitted
        # (requires trace capture fixture)
```

**Coverage target:** >85%

### 5. Create Contract Conformance Test (10 min)

**File:** `tests/contract/test_my_retriever_conformance.py`

```python
import pytest
from modular_rag.retrieval.my_retriever import {RetrieverName}
from modular_rag.contracts.retrieval import RetrieverProtocol
from modular_rag.core.models import SearchResult

def test_protocol_implementation():
    """Verify {RetrieverName} implements RetrieverProtocol."""
    assert issubclass({RetrieverName}, RetrieverProtocol)
    
    # Check required methods
    assert hasattr({RetrieverName}, 'retrieve')
    assert callable(getattr({RetrieverName}, 'retrieve'))

def test_retrieve_returns_correct_type(retriever):
    """Verify retrieve() returns List[SearchResult]."""
    results = retriever.retrieve("test", k=5)
    assert isinstance(results, list)
    assert all(isinstance(r, SearchResult) for r in results)

def test_trace_step_emitted():
    """Verify TraceStep is emitted."""
    # Implementation depends on trace capture
```

### 6. Register in Registry (5 min)

**File:** `src/modular_rag/orchestration/registry.py`

```python
from modular_rag.retrieval.my_retriever import {RetrieverName}

def _create_{retriever_name}(config: dict) -> RetrieverProtocol:
    """Factory for {RetrieverName}."""
    return {RetrieverName}(
        config=config,
        **config.get("params", {})
    )

# Register in BUILT_IN_RETRIEVERS
BUILT_IN_RETRIEVERS = {
    # ... existing retrievers
    "{retriever_name}": _create_{retriever_name},
}
```

### 7. Create Manifest Example (5 min)

**File:** `manifests/presets/local-{retriever_name}-rag.yaml`

```yaml
version: 1.0

retrieval:
  retrievers:
    - type: {retriever_name}
      {{configuration_params}}
      k: 10
      
  reranker:
    type: cross_encoder
    model: mxbai-rerank-v1
    top_k: 5

generation:
  generator:
    type: openai
    model: gpt-4
```

### 8. Validate Architecture (5 min)

**Checklist:**
- [ ] No cross-domain imports (only contracts + core)
- [ ] External libraries lazy-imported
- [ ] TraceStep emitted for all operations
- [ ] Unit tests cover >85% of code
- [ ] Contract conformance test passing
- [ ] Registered in registry
- [ ] Manifest example provided
- [ ] Performance benchmarked

**Validation commands:**
```bash
# Quick check
./scripts/check.sh quick

# Full check
./scripts/check.sh full

# Run retriever-specific tests
pytest tests/unit/retrieval/test_my_retriever.py -v
pytest tests/contract/test_my_retriever_conformance.py -v
```

### 9. Document & Submit (10 min)

**Create ADR if significant:**
- File: `docs/adr/000X-add-{retriever_name}.md`
- Title: "Add {RetrieverName} Implementation"
- Include: Why, How, Trade-offs

**Update documentation:**
- Add to `docs/guides/retriever-implementations.md`
- Include performance characteristics
- Document configuration options

**Commit changes:**
```bash
git checkout -b feature/add-{retriever_name}-retriever
git add src/modular_rag/retrieval/{retriever_name}.py tests/
git commit -m "feat: Add {RetrieverName} retriever implementation"
git push origin feature/add-{retriever_name}-retriever
```

## Success Criteria

✅ RetrieverProtocol fully implemented
✅ All methods have type hints
✅ Lazy imports on external libraries
✅ TraceStep emission for observability
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ Registered in ComponentRegistry
✅ Manifest example provided
✅ Architecture rules verified
✅ Documentation complete

## Time Estimate

**Total:** 1.5-2 hours for a straightforward retriever
- Setup: 10 min
- Implementation: 30 min
- Testing: 35 min
- Integration: 20 min
- Documentation: 15 min
