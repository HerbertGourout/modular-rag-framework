# CLAUDE.md — Contracts Module

This file provides guidance for Claude working on the contracts (Protocol definitions) layer. Read this **before editing any file in this directory**.

---

## ⚠️ Architecture Critical

The contracts module defines **Protocols** that every implementation must satisfy. Changes here propagate to:
- All implementations (adapters, domain modules)
- All tests (contract conformance tests)
- All type checking and IDE support

**Any change requires careful consideration and likely an ADR.**

---

## Rule 1: Protocol First, Implementation Second

### Never Change a Protocol Without ADR

If a Protocol needs change:
1. Create new ADR in `docs/adr/` explaining why
2. Discuss with architecture team
3. Plan migration for existing implementations
4. Update ALL implementations simultaneously
5. Commit ADR + Protocol change + implementation updates together

### ❌ FORBIDDEN
```python
# ❌ Just adding fields to a Protocol without ADR
# This breaks all existing implementations!
class Retriever(Protocol):
    def retrieve(self, query: str) -> List[Document]:
        ...
    
    def retrieve_with_scores(self, query: str) -> List[Tuple[Document, float]]:
        ...  # NEW FIELD — breaks all implementations!
```

### ✅ ALLOWED
```python
# ✅ New Protocol in new version
# Implementations opt-in via separate implementation class
class RetrieverV2(Protocol):
    """New interface for V2 hybrid retrieval."""
    def retrieve(self, query: str, config: RetrievalConfig) -> List[Document]:
        ...
    
    def retrieve_with_scores(self, query: str, config: RetrievalConfig) -> List[Tuple[Document, float]]:
        ...

# ✅ Backward compat: existing Retriever unchanged
# implementations choose to implement Retriever or RetrieverV2
```

---

## Rule 2: Protocols Define Interface, Not Implementation

### Structure of a Protocol

```python
from typing import Protocol
from modular_rag.core.models import Document, Query

class MyComponent(Protocol):
    """Clear docstring explaining purpose and responsibilities.
    
    This component is responsible for [what it does].
    It is used by [who uses it].
    """
    
    def do_something(self, input_data: str) -> str:
        """Execute the core operation.
        
        Args:
            input_data: Description of input format
            
        Returns:
            Description of output format
            
        Raises:
            ValueError: When input is invalid
            SomeError: When operation fails
        """
        ...
    
    def name(self) -> str:
        """Return the component's identifier.
        
        Used for logging, manifest registration, etc.
        """
        ...
```

### ❌ FORBIDDEN in Protocols

```python
# ❌ Implementation details in Protocol
class BadProtocol(Protocol):
    def do_something(self):
        # This is implementation, not interface!
        self.cache = {}
        return self.cache.get("key")
```

### ✅ ALLOWED

```python
# ✅ Interface only
class GoodProtocol(Protocol):
    def do_something(self) -> Any:
        """Execute operation. May use internal caching."""
        ...
```

---

## Rule 3: Documentation is Part of the Contract

### Protocol Docstrings Must Include

- **Purpose**: What is this component for?
- **Responsibility**: What does it do? What does it NOT do?
- **Usage**: How is it used in the framework?
- **Example**: Minimal working example
- **Errors**: What can go wrong?

### Example

```python
class Embedder(Protocol):
    """Generate embeddings (vector representations) of text.
    
    **Responsibility:**
    - Take text and return fixed-size dense vector
    - Support batch operations for efficiency
    - Be deterministic (same input → same embedding)
    
    **NOT Responsible for:**
    - Storing embeddings (that's VectorStore's job)
    - Ranking/reranking (that's Reranker's job)
    - Normalizing text (that's Ingestion's job)
    
    **Usage:**
    Used by VectorRetriever to encode queries and documents for similarity search.
    Registered in manifest under "embedder" component type.
    
    **Example** (real API — `ComponentRegistry` has no `get_component()` method; components
    come off the wired `Container`):
    ```python
    container = create_default_registry().wire(manifest)
    embedder = container.embedder
    doc_vectors = embedder.embed(["hello world", "goodbye world"])
    ```
    
    **Errors:**
    - ValueError if text is empty
    - RuntimeError if model not loaded
    """
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts — the real Protocol (contracts/embeddings.py) has no
        separate single-text method; call embed(["one text"]) for a single item."""
        ...
    
    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Async variant."""
        ...
    
    def dimensions(self) -> int:
        """Return embedding vector dimension."""
        ...
    
    def name(self) -> str:
        """Return component identifier."""
        ...
```

---

## Rule 4: Backward Compatibility

### When to Keep Old Protocols

**Keep** if:
- Existing implementations still work
- No urgent need to migrate

**Change** if:
- Security or correctness issue
- Major architectural change (requires ADR)
- V2+ feature that needs new interface

### Migration Path

```python
# OLD (keep for backward compat)
class RetrieverV1(Protocol):
    def retrieve(self, query: str) -> List[Document]:
        ...

# NEW (opt-in for V2 features)
class RetrieverV2(Protocol):
    def retrieve(self, query: str, config: RetrievalConfig) -> List[Document]:
        ...
    
    def retrieve_with_reasoning(self, query: str) -> List[Tuple[Document, str]]:
        # New capability in V2
        ...

# Implementations choose:
class HybridRetriever(RetrieverV2):
    # Supports both old and new interface
    def retrieve(self, query: str, config: RetrievalConfig = None) -> List[Document]:
        ...
```

---

## Rule 5: Testing Contracts

### Contract Conformance Tests

Every Protocol must have matching test in `tests/contract/`:

```python
# tests/contract/test_retrieval_conformance.py (real file — see it for the actual pattern)

from modular_rag.contracts import Retriever
from modular_rag.core.models.query import Query
from modular_rag.retrieval.retrievers.bm25 import BM25Retriever  # real path: retrievers/ subpackage

def test_bm25_is_retriever():
    """Verify BM25Retriever implements the Retriever Protocol."""
    retriever = BM25Retriever()

    # Check Protocol conformance
    assert isinstance(retriever, Retriever)

    # Check required methods (Retriever has retrieve, aretrieve, name — see contracts/retrieval.py)
    assert hasattr(retriever, 'retrieve')
    assert hasattr(retriever, 'aretrieve')
    assert hasattr(retriever, 'name')

def test_retriever_output_format():
    """Verify retrieve() returns correct format — takes a Query object, not a bare string."""
    from modular_rag.core.models.retrieved import RetrievedChunk

    retriever = BM25Retriever()
    results = retriever.retrieve(Query(text="test query"), k=10)

    assert isinstance(results, list)
    assert all(isinstance(r, RetrievedChunk) for r in results)
```

---

## Rule 6: Extending Contracts (Rare, Needs Justification)

### When to Extend

**Only** extend a Protocol if:
- Multiple implementations need the new capability
- Capability is core to the component's responsibility
- Benefits outweigh migration cost

### How to Extend

```python
# Instead of modifying Retriever, create new capability interface:

class RankedRetriever(Protocol):
    """Retriever that returns results with relevance scores."""
    
    def retrieve_ranked(self, query: str) -> List[Tuple[Document, float]]:
        """Retrieve with scores (0.0-1.0)."""
        ...

# Implementations opt-in:
class HybridRetriever(Retriever, RankedRetriever):
    def retrieve(self, query: str) -> List[Document]:
        ...
    
    def retrieve_ranked(self, query: str) -> List[Tuple[Document, float]]:
        ...
```

---

## Checklist Before Editing

- [ ] Is this a documentation-only change? (✅ OK)
- [ ] Is this a type annotation improvement? (✅ OK)
- [ ] Does this add a new method to an existing Protocol? (❌ Needs ADR)
- [ ] Does this remove a method? (❌ Needs ADR + migration plan)
- [ ] Does this change method signature? (❌ Needs ADR + migration plan)
- [ ] Are there existing implementations? (Must update all or create new version)
- [ ] Is there an ADR justifying this change? (Required for any structural change)

---

## References

- [ADR-0002: Contracts and Plugins](../../../docs/adr/0002-contracts-and-plugins.md)
- [.claude/.instructions.md](../../../.claude/.instructions.md) — Architecture rules
- [CONTRIBUTING.md](../../../CONTRIBUTING.md) — Development workflow

