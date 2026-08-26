---
paths:
  - "src/modular_rag/adapters/**/*.py"
description: "Rules for implementing adapters: external bindings, lazy imports, Protocol implementation, and dependency isolation."
version: "1.0"
lastUpdated: "2026-06-19"
---

# Règles — édition des adaptateurs (adapters/)

The adapters layer is where external library dependencies live. This module implements Protocols defined in `contracts/` but always imports heavy third-party libraries lazily to keep domain modules lightweight and testable.

---

## 1. Lazy Imports (Mandatory Rule)

### Rule: Heavy Dependencies Must Be Imported Inside Methods, Never at Module Level
Heavy external libraries must be imported **inside the method that uses them**, not at the top of the file. This prevents domain modules from requiring large downloads and keeps tests fast.

### Heavy Libraries (Lazy Import Required)
```
- qdrant-client       (Qdrant vectorstore)
- rank-bm25           (BM25 retrieval)
- sentence-transformers (Hugging Face embeddings, ~2 GB)
- openai              (OpenAI LLM)
- anthropic           (Anthropic LLM)
- fitz                (PDF parsing)
- Any large ML models (transformers, etc.)
```

### ❌ WRONG Pattern
```python
# ❌ Module-level import — blocks import even if feature isn't used
from sentence_transformers import SentenceTransformer
import qdrant_client

class HFEmbedder:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()
```

**Problem**: Importing `HFEmbedder` requires downloading sentence-transformers (2 GB), even if the user only needs BM25.

### ✅ CORRECT Pattern
```python
# ✅ Lazy import inside method — only loads when actually used

from modular_rag.contracts.embeddings import Embedder

class HFEmbedder(Embedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None  # Lazy-loaded
    
    def _get_model(self):
        """Load model on first access (lazy initialization)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # ← Lazy import
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the lazy-loaded model."""
        model = self._get_model()
        return model.encode(texts).tolist()
    
    def embed_single(self, text: str) -> list[float]:
        """Embed a single text."""
        model = self._get_model()
        return model.encode([text])[0].tolist()
```

**Benefits**: 
- `import HFEmbedder` is fast (no sentence-transformers download)
- Model loads only when `embed()` is called
- Tests can mock the internal model
- Other embedders don't need sentence-transformers

### Another Example: QdrantStore
```python
class QdrantStore(Indexer):
    def __init__(self, url: str = "http://localhost:6333", collection: str = "default"):
        self.url = url
        self.collection = collection
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient  # ← Lazy import
            self._client = QdrantClient(url=self.url)
        return self._client
    
    def index(self, chunks: list[Chunk]) -> None:
        client = self._get_client()
        # Use client...
    
    def search(self, query_vector: list[float], k: int = 10) -> list[Chunk]:
        client = self._get_client()
        # Use client...
```

---

## 2. Protocol Implementation Checklist

### Rule: Every Adapter Must Implement a Protocol from `contracts/`
Before creating an adapter, ensure a Protocol exists that defines its interface.

### Checklist Before Creating Adapter
- [ ] **Protocol exists** in `contracts/` (e.g., `contracts/embeddings.py`)
- [ ] **Protocol fully documented** (docstrings, type hints)
- [ ] **All methods typed** with input/output types
- [ ] **All abstract methods** will be implemented in the adapter

### Example: Implementing Embedder Protocol
```python
# contracts/embeddings.py (Protocol)
from typing import Protocol, list

class Embedder(Protocol):
    """Interface for embedding models."""
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        ...
    
    def embed_single(self, text: str) -> list[float]:
        """Embed a single text (optional performance optimization)."""
        ...

# adapters/embeddings/hf_embedder.py (Implementation)
from modular_rag.contracts.embeddings import Embedder

class HFEmbedder(Embedder):  # ← Implements Protocol
    """Hugging Face embeddings via sentence-transformers."""
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        return model.encode(texts).tolist()
    
    def embed_single(self, text: str) -> list[float]:
        model = self._get_model()
        return model.encode([text])[0].tolist()
```

### Conformance Testing
Every Protocol implementation must pass conformance tests:

```python
# tests/contract/test_embedder_conformance.py
import pytest
from modular_rag.contracts.embeddings import Embedder
from modular_rag.adapters.embeddings import HFEmbedder

@pytest.mark.parametrize("embedder_class", [HFEmbedder])
def test_embedder_implements_protocol(embedder_class):
    """Verify all Embedder implementations conform to Protocol."""
    embedder = embedder_class()
    assert isinstance(embedder, Embedder)
    
    # Test interface
    texts = ["Hello", "World"]
    embeddings = embedder.embed(texts)
    assert len(embeddings) == 2
    assert all(isinstance(e, list) for e in embeddings)
```

---

## 3. Never Import from Domain Modules

### Rule: Adapters May NOT Import from Domain Modules
Adapters sit **above** domain modules in the hexagonal architecture. They may only import from `contracts/` and `core/`.

### ❌ FORBIDDEN Imports
```python
# ❌ Adapter importing from domain module
from modular_rag.retrieval.bm25 import BM25Retriever
from modular_rag.generation.openai import OpenAIGenerator

# This breaks hexagonal layering!
```

### ✅ ALLOWED Imports
```python
# ✅ Adapters import from contracts and core
from modular_rag.contracts.embeddings import Embedder
from modular_rag.contracts.vectorstores import Indexer
from modular_rag.core.models import Chunk, Document

# ✅ Adapters import external libraries (lazily)
from sentence_transformers import SentenceTransformer  # Inside method only!
```

### Why This Matters
If adapters imported from domain modules, it would create circular dependencies:
- `retrieval/` → `contracts/` → `adapters/` → `retrieval/` ❌ CYCLE!

Instead:
- `retrieval/` → `contracts/` → `adapters/` ✅ ONE DIRECTION

---

## 4. Dependency Isolation: Tests Without External Services

### Rule: Adapter Unit Tests Should Not Require External Services
Adapters may connect to external services (Qdrant, OpenAI, Hugging Face), but **unit tests** should run without them.

### Strategies for Isolation

#### Strategy 1: Mock External Services
```python
# tests/unit/adapters/test_hf_embedder.py
import pytest
from unittest.mock import MagicMock, patch

def test_hf_embedder_embed():
    """Test HFEmbedder without downloading the model."""
    with patch('modular_rag.adapters.embeddings.hf_embedder.SentenceTransformer') as mock_model:
        # Mock the sentence-transformers library
        mock_model.return_value.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
        
        embedder = HFEmbedder(model_name="all-MiniLM-L6-v2")
        result = embedder.embed(["Hello", "World"])
        
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        mock_model.return_value.encode.assert_called_once()
```

#### Strategy 2: Use In-Memory Alternatives
```python
# tests/unit/adapters/test_qdrant_store.py
import pytest
from unittest.mock import MagicMock

def test_qdrant_store_index():
    """Test QdrantStore without running Qdrant server."""
    # Mock the Qdrant client
    mock_client = MagicMock()
    
    store = QdrantStore(url="http://localhost:6333")
    store._client = mock_client  # Inject mock
    
    chunks = [Chunk(text="Hello", embedding=[0.1, 0.2])]
    store.index(chunks)
    
    # Verify interaction
    mock_client.upsert.assert_called_once()
```

#### Strategy 3: Integration Tests (Separate Scope)
For tests that require real external services, use `@pytest.mark.integration`:

```python
# tests/integration/test_qdrant_store.py
import pytest

@pytest.mark.integration  # ← Requires Qdrant on localhost:6333
def test_qdrant_store_real_server():
    """Test QdrantStore with real Qdrant instance."""
    store = QdrantStore(url="http://localhost:6333")
    chunks = [Chunk(text="Hello", embedding=[0.1, 0.2])]
    
    store.index(chunks)
    results = store.search([0.1, 0.2], k=1)
    
    assert len(results) > 0
```

---

## 5. Configuration via Manifest YAML

### Rule: All Adapter Configuration Goes to Manifest, Never Hardcoded
Adapters must be configurable via YAML manifests. No hardcoded URLs, API keys, or paths.

### ❌ WRONG
```python
class OpenAIGenerator:
    def __init__(self):
        self.api_key = "sk-..."  # ❌ Hardcoded!
        self.model = "gpt-4"     # ❌ Hardcoded!
```

### ✅ CORRECT
```python
class OpenAIGenerator:
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model

# In app/default_factories.py, inside register_defaults():
reg.register("generator", "openai", lambda cfg: OpenAIGenerator(**cfg.config))
# api_key isn't read from a custom env var — if the manifest's config.api_key is left
# unset, OpenAIGenerator passes None through and the SDK itself falls back to its own
# standard OPENAI_API_KEY env var (app/settings.py's MRAG_-prefixed Settings class is
# orphaned; nothing in this wiring path ever constructs it)

# In manifests/my_pipeline.yaml:
components:
  generator:
    type: "openai"
    config:
      model: "gpt-4o-mini"
      # api_key omitted here on purpose — falls back to OPENAI_API_KEY in the environment
```

---

## 6. Error Handling in Adapters

### Rule: Raise Custom Errors from `core.errors`, Never External Library Exceptions
Adapters must translate external library exceptions into project-specific errors for consistency.

### ❌ WRONG
```python
def embed(self, texts: list[str]) -> list[list[float]]:
    model = self._get_model()
    return model.encode(texts).tolist()  # Raises torch.cuda.OutOfMemoryError ❌
```

### ✅ CORRECT
```python
from modular_rag.core.errors import EmbeddingError

def embed(self, texts: list[str]) -> list[list[float]]:
    try:
        model = self._get_model()
        return model.encode(texts).tolist()
    except Exception as e:
        raise EmbeddingError(f"Embedding failed: {e}") from e
```

### Custom Errors (from `core/errors.py`)
```python
IngestError         # Parsing, chunking, normalization failed
RetrievalError      # Vector store, BM25, reranking failed
GenerationError     # LLM call failed
EmbeddingError      # Embedding model failed
SecurityError       # Guard evaluation failed
IndexError          # Vector store indexing failed
```

---

## 7. Performance Considerations

### Lazy Loading Trade-off
- **Benefit**: Fast import time, small memory footprint
- **Cost**: First call adds ~500ms latency (model download + initialization)
- **Mitigation**: Pre-warm models in `app/bootstrap.py` if needed

### Caching
If your adapter uses an expensive resource, cache it:

```python
class HFEmbedder:
    _model_cache = {}  # Class-level cache
    
    def _get_model(self):
        key = self.model_name
        if key not in HFEmbedder._model_cache:
            from sentence_transformers import SentenceTransformer
            HFEmbedder._model_cache[key] = SentenceTransformer(key)
        return HFEmbedder._model_cache[key]
```

---

## 8. Adapter File Structure

### Directory Layout
```
src/modular_rag/adapters/
├── embeddings/
│   ├── hf_embedder.py
│   ├── openai_embedder.py
│   └── deterministic_embedder.py
├── vectorstores/
│   ├── qdrant_store.py
│   └── qdrant_sparse_store.py
├── llms/
│   └── langgraph_engine.py
├── auth/
│   └── keycloak_verifier.py
├── audit/ and lifecycle/      (durable PostgreSQL adapters)
├── postgres/                  (migration runner and packaged SQL)
├── observability/             (OpenTelemetry tracer and meter adapters)
└── graphstores/ and search/   (empty delegated extension targets)
```

### Rules
- Each adapter in its own file
- `__init__.py` exports public classes (note: as of Lot 10, `adapters/` subdirectories in this
  repo are plain namespace packages with no `__init__.py` — submodules are imported by their full
  path, e.g. `from modular_rag.adapters.auth.keycloak_verifier import KeycloakTokenVerifier`)
- `.gitkeep` for stubs not yet implemented
- `llms/` contains the selectable LangGraph adapter. `graphstores/` and `search/` are still empty;
  any future code there must not become a native reimplementation of GraphRAG traversal or generic
  agent orchestration. `auth/` implements `contracts/identity.py`'s
  `TokenVerifier` Protocol against Keycloak specifically (Lot 11b) — tenant-isolation
  *enforcement* against the verified identity lives in `security/policies/`, not here.

---

## 9. Testing Adapters

### Unit Tests (Fast, No External Services)
```python
# tests/unit/adapters/test_hf_embedder.py
def test_hf_embedder_lazy_loads_model():
    embedder = HFEmbedder()
    assert embedder._model is None  # Not loaded yet
    
    embedder.embed(["test"])
    assert embedder._model is not None  # Lazy loaded
```

### Integration Tests (Requires External Service)
```python
# tests/integration/test_qdrant_store.py
@pytest.mark.integration
def test_qdrant_store_indexes_and_searches():
    store = QdrantStore(url="http://localhost:6333")
    chunks = [
        Chunk(text="Hello", embedding=[0.1, 0.2, 0.3]),
        Chunk(text="World", embedding=[0.9, 0.8, 0.7])
    ]
    store.index(chunks)
    results = store.search([0.1, 0.2, 0.3], k=1)
    assert results[0].text == "Hello"
```

---

## 10. Summary: Adapter Dos & Don'ts

### ✅ DO
- Lazy import heavy libraries inside methods
- Implement Protocols from `contracts/`
- Translate external exceptions to custom errors
- Configure via manifest YAML + environment variables
- Test with mocks in unit scope
- Test with real services in integration scope
- Isolate adapter dependencies from domain modules

### ❌ NEVER
- Import heavy libraries at module level
- Import from domain modules (`retrieval/`, `generation/`, etc.)
- Hardcode configuration (URLs, API keys, paths)
- Let external exceptions propagate unhandled
- Couple adapters to each other
- Implement domain logic in adapters
- Create new adapter without a Protocol in `contracts/`

---

Good luck implementing adapters!
