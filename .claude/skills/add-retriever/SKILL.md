---
name: add-retriever
description: Step-by-step workflow for implementing a new retriever following the Retriever contract
---

# Add Retriever Skill

> **Corrected 2026-08-06** (documentation-utility pass): this file previously described a
> fictional `RetrieverProtocol` (`retrieve(query: str, k, **kwargs) -> List[SearchResult]`,
> async-only), a `SearchResult` type, a `RagConfig` class, a `TraceStep(component=, method=)`
> constructor, and a `BUILT_IN_RETRIEVERS` registry dict — none of which exist. Rewritten below
> against the real `Retriever` protocol (`src/modular_rag/contracts/retrieval.py`), the real
> `RetrievedChunk` type (`src/modular_rag/core/models/retrieved.py`), and the real registration
> pattern (`src/modular_rag/app/default_factories.py`), using `VectorRetriever`
> (`src/modular_rag/retrieval/retrievers/vector.py`) as the reference implementation.

## State of the Art First (mandatory)

Before designing the retriever, read [docs/research/DIGEST-retrieval.md](../../../docs/research/DIGEST-retrieval.md), [docs/research/DIGEST-evaluation.md](../../../docs/research/DIGEST-evaluation.md) and [docs/research/DIGEST-overviews.md](../../../docs/research/DIGEST-overviews.md); cite the arXiv id backing each design choice (fusion, reranking, metric targets). If a choice contradicts the digests, justify it explicitly in the MR.

## Parameters (advisory — not schema-validated by Claude Code)

Claude Code skills don't support typed/validated parameters in frontmatter; describe these to the agent in your invocation prompt instead:

- `retriever_type` (enum, required) — one of: ['vector', 'bm25', 'hybrid', 'semantic', 'graph']
- `retriever_name` (string, required) — pattern: `^[A-Z][a-zA-Z0-9]*Retriever$`
- `external_library` (string, optional) — Optional external library dependency (e.g., qdrant-client)

_Originally authored as a workflow for `retrieval-specialist`, invoked as `/add-retriever`._

Guided workflow for implementing a new retriever component against the `Retriever` contract.

## When to Use

- Implementing a new retrieval method (vector, BM25, hybrid)
- Integrating external retrieval systems
- Optimizing retrieval for specific domains
- Adding specialized retrievers (graph-based, semantic — check
  [ADR-0005](../../../docs/adr/0005-document-ai-control-plane-boundary.md) first: GraphRAG
  traversal is delegated to the selected external engine, not a native retriever target)

## Workflow Steps

### 1. Verify Protocol Compliance (5 min)

**Actions:**
- Open `src/modular_rag/contracts/retrieval.py`
- Review the `Retriever` protocol
- Required methods:
  ```python
  def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...
  async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...
  def name(self) -> str: ...
  ```
- Both `retrieve()` and `aretrieve()` are required — the real retrievers implement the sync
  path and have `aretrieve()` delegate to it (`return self.retrieve(query, k)`), rather than
  being async-only.

### 2. Setup Implementation Directory (5 min)

**Structure:**
```
src/modular_rag/retrieval/retrievers/
├── __init__.py
├── vector.py         (existing)
├── bm25.py            (existing)
├── hybrid.py          (existing)
└── {retriever_name}.py   (NEW)
```

**Create file:**
```python
# src/modular_rag/retrieval/retrievers/{retriever_name}.py
from __future__ import annotations

import structlog

from modular_rag.core.errors import RetrievalError
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk

log = structlog.get_logger(__name__)


class {RetrieverName}:
    """{{Description of retriever}}

    External dependency: {{external_library}} (lazy imported).
    """

    def __init__(self, k: int = 10, **kwargs) -> None:
        self.k = k
        # store constructor config here; lazy-import heavy dependencies inside retrieve()

    def name(self) -> str:
        return "{retriever_name}"

    def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        # Lazy import heavy dependencies here, not at module level
        chunks: list[RetrievedChunk] = []
        log.debug("{retriever_name}.retrieved", chunks=len(chunks), query_id=query.id)
        return chunks

    async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
        return self.retrieve(query, k)
```

Trace emission for retrieval is the **caller's** responsibility in the current codebase
(`RAGEngine.answer()` wraps the `retrieve()`/`aretrieve()` call and emits the `TraceStep`
itself) — a new retriever does not need to construct or add its own `TraceStep`, only return
`list[RetrievedChunk]`.

### 3. Implement Core Methods (20-30 min)

**Pattern for retrieve() with a store dependency injected post-wiring** (see `VectorRetriever`
for the full version): store the dependency as `None` in `__init__`, raise `RetrievalError` with
a clear message if it's still `None` when `retrieve()` is called (the registry wires it in after
construction, per `orchestration/registry.py`'s `wire()` step), and never import the heavy
client library at module level.

```python
def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]:
    if self._store is None:
        raise RetrievalError(
            "{RetrieverName} requires a store — wire one via the manifest indexer field."
        )
    # 1. Process query, 2. search, 3. build RetrievedChunk list, 4. log/return
    ...
```

### 4. Create Unit Tests (15-20 min)

**File:** `tests/unit/retrieval/retrievers/test_{retriever_name}.py`

```python
import pytest

from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.{retriever_name} import {RetrieverName}


class Test{RetrieverName}:

    @pytest.fixture
    def retriever(self):
        return {RetrieverName}(k=10)

    def test_retrieve_success(self, retriever):
        query = Query(text="What is RAG?")
        results = retriever.retrieve(query, k=10)
        assert len(results) <= 10

    def test_aretrieve_delegates_to_retrieve(self, retriever):
        import asyncio
        query = Query(text="What is RAG?")
        results = asyncio.run(retriever.aretrieve(query, k=5))
        assert isinstance(results, list)
```

**Coverage target:** >85%

### 5. Create Contract Conformance Test (10 min)

**File:** `tests/contract/test_retrieval_conformance.py` (add a case to the existing file — see
that file for the pattern)

```python
from modular_rag.contracts.retrieval import Retriever
from modular_rag.retrieval.retrievers.{retriever_name} import {RetrieverName}


def test_{retriever_name}_conforms_to_retriever_protocol():
    instance = {RetrieverName}()
    assert isinstance(instance, Retriever)
```

### 6. Register in Registry (5 min)

**File:** `src/modular_rag/app/default_factories.py` — add the import inside
`register_defaults()` (all component imports there are function-local) and one `reg.register(...)`
line, following the existing `"vector"`/`"hybrid"` retriever entries:

```python
from modular_rag.retrieval.retrievers.{retriever_name} import {RetrieverName}
...
reg.register("retriever", "{retriever_name}", lambda cfg: {RetrieverName}(**cfg.config))
```

### 7. Create Manifest Example (5 min)

Only `manifests/presets/local-hybrid-rag.yaml` wires end-to-end today (see
`manifests/README.md`'s Runnable vs. Blueprint table) — either add your new retriever as a
second option in a copy of that manifest and confirm it actually wires with
`load_pipeline(...)`, or clearly mark a new preset file as Blueprint until it's verified
Runnable.

```yaml
retrieval:
  retriever:
    type: "{retriever_name}"
    config:
      k: 10
```

### 8. Validate Architecture (5 min)

**Checklist:**
- [ ] No cross-domain imports (only contracts + core)
- [ ] External libraries lazy-imported
- [ ] Unit tests cover >85% of code
- [ ] Contract conformance test passing
- [ ] Registered in `app/default_factories.py`
- [ ] Manifest example provided (and confirmed Runnable, or marked Blueprint)

**Validation commands:**
```bash
# Quick check
./scripts/check.sh quick

# Full check
./scripts/check.sh full

# Run retriever-specific tests
pytest tests/unit/retrieval/retrievers/test_{retriever_name}.py -v
pytest tests/contract/test_retrieval_conformance.py -v
```

### 9. Document & Submit (10 min)

**Create ADR if significant:**
- File: `docs/adr/000X-add-{retriever_name}.md`
- Title: "Add {RetrieverName} Implementation"
- Include: Why, How, Trade-offs

There is no dedicated per-retriever documentation file in this repo today — if the new
retriever's behavior warrants standalone docs, add a short section to
[docs/architecture/data-model.md](../../../docs/architecture/data-model.md) rather than
inventing a new guide file.

**Commit changes:**
```bash
git checkout -b feature/add-{retriever_name}-retriever
git add src/modular_rag/retrieval/retrievers/{retriever_name}.py tests/
git commit -m "feat: Add {RetrieverName} retriever implementation"
git push origin feature/add-{retriever_name}-retriever
```

## Success Criteria

✅ `Retriever` protocol fully implemented (`retrieve`, `aretrieve`, `name`)
✅ All methods have type hints
✅ Lazy imports on external libraries
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ Registered in `app/default_factories.py`
✅ Manifest example provided (and confirmed Runnable, or marked Blueprint)
✅ Architecture rules verified

## Time Estimate

**Total:** 1.5-2 hours for a straightforward retriever
- Setup: 10 min
- Implementation: 30 min
- Testing: 35 min
- Integration: 20 min
- Documentation: 15 min
