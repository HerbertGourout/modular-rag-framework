---
title: "Complete Claude Code Development Guide"
description: "Comprehensive guide for building features with Claude Code while respecting all architecture, security, and validation rules"
version: "1.1"
lastUpdated: "2026-08-06"
audience: ["Developers", "Architects", "Tech Leads"]
---

# Complete Claude Code Development Guide

**For**: All developers building on the Modular RAG Framework  
**Purpose**: Master the complete workflow for implementing features using Claude Code while respecting architecture rules, security layers, and validation standards  
**Time to read**: 45 minutes  
**Time to implement**: 1-2 hours per feature

---

## Table of Contents

1. [Getting Started in 5 Minutes](#getting-started-in-5-minutes)
2. [The Complete Workflow](#the-complete-workflow)
3. [Architecture Rules You Must Know](#architecture-rules-you-must-know)
4. [Pattern Library — Reusable Solutions](#pattern-library--reusable-solutions)
5. [Real-World Examples](#real-world-examples)
6. [Validation & Testing](#validation--testing)
7. [Debugging & Troubleshooting](#debugging--troubleshooting)
8. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)
9. [Quick Reference Card](#quick-reference-card)

---

## Getting Started in 5 Minutes

### 1️⃣ Prerequisites (< 1 min)

Verify your environment is ready:

```bash
# Clone repo and install
git clone <repo-url> && cd modular-rag-framework
pip install -e ".[v1,dev]"

# Verify installation
python -c "import modular_rag; print('✓ Ready')"

# Copy environment template
cp .env.example .env
# Edit .env with your values (OPENAI_API_KEY / ANTHROPIC_API_KEY — the SDKs' own
# standard names, not MRAG_OPENAI_API_KEY: app/settings.py's MRAG_-prefixed
# Settings class is declared but never actually read in the pipeline-wiring path)
```

### 2️⃣ Know the Three Core Rules (< 2 min)

**Rule 1: Hexagonal Layering**
```
cli/api → app → orchestration → contracts/core
                                    ↑
                     domain modules  ├─ adapters
                                    ↑
```

**Rule 2: No Cross-Domain Imports**
- ✅ `retrieval/` imports `contracts/retrieval.py` + `core/models/`
- ❌ `retrieval/` imports `generation/`

**Rule 3: Wire via YAML + Registry**
- ❌ No Python wiring inside modules
- ✅ Register in `orchestration/registry.py` + select in YAML manifests

### 3️⃣ Know Your Commands (< 2 min)

```bash
# After any code change
./scripts/check.sh quick          # Syntax check (30s)

# Before merge
./scripts/check.sh full           # Unit + contract tests (2-5 min)

# With external services
./scripts/check.sh integration    # Add integration tests
./scripts/check.sh e2e            # Full pipeline
```

### 4️⃣ Your First Claude Interaction (< 2 min)

```
You: "Help me add a BM25 retriever"
Claude: [Explains what it will do, checks rules]

You: "/full-check"
Claude: [Runs comprehensive validation]

You: [Review output] "Looks good, merge!"
```

---

## The Complete Workflow

> **Renamed 2026-08-06** (documentation-utility pass): phases 2, 4, and 5 below were previously
> called DESIGN, VALIDATE, and REVIEW — renamed to PLAN, VERIFY, and DELIVER to match the single
> canonical 5-step scheme now defined in
> [CLAUDE-CODE-COMPLETE-GUIDE.md § The 5-Step Workflow](./CLAUDE-CODE-COMPLETE-GUIDE.md#the-5-step-workflow).
> The two files previously used different step counts (5 vs 6) and, worse, used "VALIDATE" for
> two different things (a pre-coding plan-approval gate there, post-implementation testing
> here) — resolved by merging into one scheme rather than maintaining two. Content below is
> unchanged; only the phase names moved to match.

### Phase 1: EXPLORE (Understand Before Acting)

**Goal**: Understand the problem, constraints, and existing patterns.

#### Step 1.1: Read Core Documentation

```bash
# Open these in your editor/browser
1. CLAUDE.md (blocks 01-09)           # Non-negotiables for this project
2. docs/architecture/overview.md      # Technical architecture
3. docs/adr/                          # Context for key decisions
```

**What to understand**:
- ✓ What version is this feature for? (V1, V2+?)
- ✓ Which layer does it belong in? (domain module, adapter, orchestration?)
- ✓ Does a Protocol already exist? (check `contracts/`)
- ✓ What will this depend on? (import rules)

#### Step 1.2: Ask Claude to Explore Existing Code

```
Prompt:
"Show me how VectorRetriever is implemented in retrieval/vector_retriever.py 
and how it's wired in orchestration/registry.py. What patterns should I follow 
for a new BM25Retriever?"

What Claude provides:
- Code references to similar implementations
- Pattern identification
- Architectural context
- Dependency graph
```

#### Step 1.3: Clarify Requirements

Ask Claude:
```
1. "What Protocol should BM25Retriever implement?"
2. "Where should tests go?"
3. "What YAML configuration will users write?"
4. "Should there be lazy imports? (yes → external lib)"
5. "Will this work with existing retrieval pipelines?"
```

**Time**: 5-15 minutes

---

### Phase 2: PLAN (Architecture First)

**Goal**: Design the component structure before writing code.

#### Step 2.1: Identify the Protocol

**Option A: Protocol Exists** (most common)
```python
# Check if it exists
from modular_rag.contracts.retrieval import RetrieverProtocol

# If yes → Implement it. Skip Step 2.2.
```

**Option B: New Protocol Needed** (rare)
```python
# Create in contracts/retrieval.py
class BM25RetrieverProtocol(Protocol):
    """BM25-based lexical retrieval protocol."""
    
    def retrieve(self, query: str, k: int) -> list[Document]:
        """Retrieve top-k documents matching query using BM25."""
        ...
```

Then create a conformance test:
```python
# tests/contract/test_retrieval_conformance.py
def test_bm25_retriever_conforms():
    retriever = BM25Retriever(index_path="...")
    assert isinstance(retriever, RetrieverProtocol)
    # Test all Protocol methods exist
```

#### Step 2.2: Choose Implementation Paths

```
Adapter vs Domain Module?

BM25Retriever is a SEARCH algorithm → Could be adapter or domain
- Path A: adapters/search/bm25_retriever.py (external library)
- Path B: retrieval/bm25_retriever.py (domain logic)

Rule: If external library (rank-bm25) → Adapter
      If pure domain logic → Domain module

For BM25: It's an external library → adapters/search/bm25_retriever.py ✓
```

#### Step 2.3: Plan Dependencies

```
What will BM25Retriever depend on?

BM25Retriever
  ├── depends on: RetrieverProtocol (contracts/retrieval.py)
  ├── depends on: Document (core/models/document.py)
  ├── lazy imports: rank-bm25 (inside __init__)
  └── NO imports from: generation/, ingestion/, security/

Document structure (from contracts):
  ├── id: str
  ├── text: str
  ├── metadata: dict
  └── embedding: Optional[list[float]]
```

**Time**: 10-15 minutes

---

### Phase 3: IMPLEMENT (Code Generation)

**Goal**: Generate code following patterns and rules.

#### Step 3.1: Write the Implementation

**Prompt Template for Claude**:

```
Context:
- Implementing: BM25Retriever adapter
- Protocol: RetrieverProtocol from contracts/retrieval.py
- Location: adapters/search/bm25_retriever.py
- External library: rank-bm25 (lazy import)
- Tests location: tests/unit/adapters/search/test_bm25_retriever.py

Rules to follow:
1. Hexagonal layering: Can only import contracts/, core/, and rank-bm25
2. Lazy imports: rank-bm25 imported inside methods, not at module level
3. Protocol compliance: All RetrieverProtocol methods implemented
4. Observability: Emit TraceStep via Trace.add_step() for retrieval
5. Type hints: Full type annotations, no Any

Generate:
1. Full implementation of BM25Retriever
2. __init__ that accepts config (corpus_path, index_path, k)
3. retrieve() method that returns List[Document]
4. Unit tests in test_bm25_retriever.py (at least 3 test cases)

Follow these patterns:
- See VectorRetriever for trace emission pattern
- See HybridRetriever for config merging pattern
- See test_vector_retriever.py for test structure
```

**What Claude generates**:
```python
# adapters/search/bm25_retriever.py
from typing import Optional
from pydantic import BaseModel
from modular_rag.contracts.retrieval import RetrieverProtocol
from modular_rag.core.models.document import Document
from modular_rag.core.observability import Trace, TraceStep

class BM25Config(BaseModel):
    corpus_path: str
    index_path: Optional[str] = None
    k: int = 5

class BM25Retriever(RetrieverProtocol):
    def __init__(self, config: BM25Config):
        self.config = config
        self.index = None
    
    def retrieve(self, query: str) -> list[Document]:
        # Lazy import here (not at module level)
        from rank_bm25 import BM25Okapi
        
        # Retrieve logic
        step = TraceStep(component="BM25Retriever", operation="retrieve")
        results = ...
        Trace.add_step(step)
        return results
```

**Key patterns Claude should follow**:
1. ✅ All imports from allowed layers
2. ✅ Lazy imports for external libs
3. ✅ Trace emission for observability
4. ✅ Type hints on all parameters
5. ✅ Docstrings explain why, not what

#### Step 3.2: Write Unit Tests

**Prompt Template**:

```
Context:
- Component: BM25Retriever
- Test location: tests/unit/adapters/search/test_bm25_retriever.py

Test cases needed:
1. test_retriever_initializes_with_valid_config()
   - Creates BM25Retriever with corpus_path
   - Verifies initialization succeeds

2. test_retrieve_returns_documents()
   - Call retrieve(query="example") with k=5
   - Assert returns list[Document]
   - Assert all documents have id, text, metadata

3. test_retrieve_respects_k_parameter()
   - Call retrieve(query="example") with k=3
   - Assert len(results) == 3

No external services needed (unit test only).
Use pytest fixtures for setup.
Mock rank-bm25 if needed to avoid installation.
```

**What Claude generates**:
```python
# tests/unit/adapters/search/test_bm25_retriever.py
import pytest
from modular_rag.adapters.search.bm25_retriever import BM25Retriever, BM25Config
from modular_rag.core.models.document import Document

@pytest.fixture
def config():
    return BM25Config(corpus_path="tests/fixtures/corpus.txt", k=5)

def test_retriever_initializes(config):
    retriever = BM25Retriever(config)
    assert retriever is not None

def test_retrieve_returns_documents(config):
    retriever = BM25Retriever(config)
    results = retriever.retrieve("test query")
    assert isinstance(results, list)
    assert all(isinstance(d, Document) for d in results)
```

#### Step 3.3: Write Contract Conformance Test

**Create**: `tests/contract/test_bm25_retriever_conformance.py`

```python
# Verify BM25Retriever properly implements RetrieverProtocol
from modular_rag.adapters.search.bm25_retriever import BM25Retriever, BM25Config
from modular_rag.contracts.retrieval import RetrieverProtocol

def test_bm25_retriever_implements_protocol():
    """BM25Retriever must implement RetrieverProtocol."""
    config = BM25Config(corpus_path="...")
    retriever = BM25Retriever(config)
    
    # Protocol methods must exist
    assert hasattr(retriever, 'retrieve')
    assert callable(retriever.retrieve)
    
    # Protocol contract: retrieve(query: str) -> list[Document]
    result = retriever.retrieve("test")
    assert isinstance(result, list)
    assert all(hasattr(d, 'id') for d in result)
    assert all(hasattr(d, 'text') for d in result)
```

**Time**: 30-45 minutes

---

### Phase 4: VERIFY (Testing & Checks)

**Goal**: Ensure code passes all validation gates.

#### Step 4.1: Run Quick Check (Before Commit)

```bash
./scripts/check.sh quick

# What it validates:
# ✓ Python syntax (ruff E, F rules)
# ✓ Undefined names (ruff F rule)
# ✓ Import order (ruff I rule)
# Time: ~30 seconds
```

**If it fails**:
```
Prompt to Claude:
"The quick check failed with: [error message]. 
Show me the fix in context (3 lines before/after the error)."

Claude provides minimal fix focused on the error.
```

#### Step 4.2: Run Full Check (Before Merge)

```bash
./scripts/check.sh full

# What it validates:
# ✓ All ruff rules (E, F, I, N, W, UP, B, C4)
# ✓ mypy type checking
# ✓ Unit tests (tests/unit/)
# ✓ Contract tests (tests/contract/)
# Time: 2-5 minutes
```

**If unit tests fail**:
```
Prompt to Claude:
"Unit tests failed: [test error]. 
The test is in tests/unit/adapters/search/test_bm25_retriever.py.
Show me the fix."

Claude analyzes failure and provides fix.
```

**If contract tests fail**:
```
Prompt to Claude:
"Contract conformance test failed. BM25Retriever must implement 
all methods in RetrieverProtocol. Show me what's missing 
by comparing the Protocol definition with the implementation."

Claude identifies missing methods or incorrect signatures.
```

#### Step 4.3: Verify with Integration Tests (Optional)

```bash
# If your component uses external services (Qdrant, LLM)
./scripts/check.sh integration

# Requires: Qdrant on localhost:6333
# Validates: Real interactions with services
```

**Time**: 5-15 minutes

---

### Phase 5: DELIVER (Refinement, Commit & Review)

**Goal**: Address feedback and finalize.

#### Step 5.1: Code Review Checklist

Before asking for code review, self-check:

```
Architectural Rules:
  ☑ No imports outside allowed layers?
  ☑ Lazy imports for heavy dependencies?
  ☑ Protocol implemented correctly?
  ☑ Trace emission for observability?

Code Quality:
  ☑ Type hints on all parameters?
  ☑ Docstrings explain why?
  ☑ No hardcoded values?
  ☑ Error handling present?

Testing:
  ☑ Unit tests cover all paths?
  ☑ Contract test verifies Protocol?
  ☑ All tests pass locally?
  ☑ Coverage > 80%?

Documentation:
  ☑ README updated if needed?
  ☑ Manifest YAML updated?
  ☑ Config options documented?
```

#### Step 5.2: Git Workflow

```bash
# 1. Create feature branch
git checkout -b feature/bm25-retriever

# 2. Commit with atomic, descriptive message
git commit -m "feat: Add BM25Retriever adapter with lazy imports

Implements hybrid search combining BM25 lexical + vector retrieval.
- BM25Retriever in adapters/search/ with RRF fusion
- Unit tests + contract conformance test
- Lazy import of rank-bm25 to keep dependencies light
- Full trace emission for observability

Adds:
- adapters/search/bm25_retriever.py (120 lines)
- tests/unit/adapters/search/test_bm25_retriever.py (80 lines)
- tests/contract/test_bm25_retriever_conformance.py (40 lines)"

# 3. Push and create PR
git push origin feature/bm25-retriever
# Open GitHub PR with checklist from CONTRIBUTING.md
```

#### Step 5.3: Address Review Feedback

```
Reviewer: "BM25Retriever should respect k from query, not just config"

Prompt to Claude:
"Show me how to modify BM25Retriever.retrieve(query: str, k: int) 
to accept k as parameter but default to self.config.k if not provided.
Show in context with type hints."

Claude provides minimal change:
```python
def retrieve(self, query: str, k: Optional[int] = None) -> list[Document]:
    k = k or self.config.k
    ...
```

**Time**: 15-30 minutes

---

## Architecture Rules You Must Know

### Rule 1: Hexagonal Layering (No Bidirectional Dependencies)

```
                 API Layer (User Facing)
                 ↓
            ┌────────────┐
            │  CLI/API   │
            └─────┬──────┘
                  ↓
            ┌────────────┐
            │   App      │  [Bootstrap, Settings, Container]
            └─────┬──────┘
                  ↓
        ┌─────────────────────┐
        │ Orchestration Layer │  [Registry, Engine, Routing]
        └─────────┬───────────┘
                  ↓
    ┌─────────────────────────────┐
    │  Contracts + Core (Shared)  │  [Protocols, Models, Exceptions]
    └─────────┬───────────────────┘
              ↑
    ┌─────────────────────────────────────┐
    │     Domain Modules (Isolated)       │  [ingestion, retrieval, generation,
    │ - NO cross-domain imports           │   security, agents, memory, eval]
    │ - Only contracts + core imports     │
    └─────────┬───────────────────────────┘
              ↑
    ┌─────────────────────────────────────┐
    │    Adapters (External Bindings)     │  [embeddings, vectorstores, LLMs]
    │ - Contract implementations          │
    │ - Heavy library imports (lazy)      │
    └─────────────────────────────────────┘
```

**Import Rules**:
| From | Can Import | Example |
|------|-----------|---------|
| `cli/`, `api/` | All layers | Import from orchestration, domain, adapters ✓ |
| `app/` | Below (orchestration, contracts, core) | Cannot import from cli/api ✗ |
| `orchestration/` | Below (contracts, core) | Cannot import from domain ✗ |
| `contracts/` | Only `core/` | Cannot import from domain ✗ |
| `core/` | Nothing from project | Pure foundation ✓ |
| Domain modules | Only `contracts/` + `core/models/` | retrieval/ ✗ import generation/ |
| `adapters/` | `contracts/` + `core/` + external libs | Cannot import domain ✗ |

**Quick Test**: If you're about to write `from retrieval.bm25_retriever import BM25Retriever` in a non-adapter file, STOP. That's violating layering. Instead:

1. If in another domain module → Add to Protocol in `contracts/`
2. If in orchestration → Get via registry + YAML config
3. If in adapter → Only if implementing same Protocol

---

### Rule 2: Lazy Imports for Heavy Dependencies

**Heavy Libraries** (must be lazy):
- `qdrant-client` (vector database)
- `rank-bm25` (BM25 search)
- `sentence-transformers` (embeddings)
- `openai` (LLM API)
- `anthropic` (LLM API)
- `fitz` (PDF parsing)
- `torch`, `transformers` (ML models)

**Pattern: Lazy Import**

```python
# ❌ WRONG (module-level import)
from rank_bm25 import BM25Okapi

class BM25Retriever:
    def retrieve(self, query: str) -> list[Document]:
        ...
```

**Problem**: Anyone importing BM25Retriever must install rank-bm25, even if they don't use it.

```python
# ✅ CORRECT (method-level import)
from modular_rag.contracts.retrieval import RetrieverProtocol

class BM25Retriever(RetrieverProtocol):
    def retrieve(self, query: str) -> list[Document]:
        # Import only when needed
        from rank_bm25 import BM25Okapi
        
        # Use rank_bm25
        bm25 = BM25Okapi(...)
        return [Document(...) for doc in results]
```

**Benefit**: Users can import BM25Retriever without installing rank-bm25 until it's actually used.

---

### Rule 3: Wire via Registry + YAML Manifests

**❌ WRONG: Direct Python Wiring**

```python
# In retrieval/hybrid_retriever.py
from adapters.search.bm25_retriever import BM25Retriever  # ✗ FORBIDDEN
from adapters.embeddings.hf_embedder import HFEmbedder   # ✗ FORBIDDEN

class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Retriever(...)  # ✗ Hard-coded dependency
        self.embedder = HFEmbedder(...)  # ✗ Hard-coded dependency
```

**Problems**:
- Hard-coded to specific implementations
- Cannot swap implementations without code change
- Breaks modularity
- Makes testing harder

**✅ CORRECT: Registry + YAML**

```python
# 1. Register in orchestration/registry.py
COMPONENT_REGISTRY = {
    "bm25_retriever": BM25Retriever,
    "hf_embedder": HFEmbedder,
}

# 2. Configure in manifests/presets/local-hybrid-rag.yaml
components:
  retriever:
    type: "hybrid_retriever"
    config:
      bm25:
        type: "bm25_retriever"
        config:
          corpus_path: "./docs/"
          k: 5
      embedder:
        type: "hf_embedder"
        config:
          model: "all-minilm-l6-v2"

# 3. Use in code (late binding)
def initialize_rag(manifest_path: str):
    config = load_yaml(manifest_path)
    retriever = registry.wire(
        config.components.retriever,
        registry=COMPONENT_REGISTRY
    )
    return retriever
```

**Benefit**: Swap implementations via YAML without code changes.

---

### Rule 4: Observability via TraceStep Emissions

**Every major operation must emit a TraceStep**:

```python
from modular_rag.core.observability import Trace, TraceStep
from modular_rag.contracts.retrieval import RetrieverProtocol

class BM25Retriever(RetrieverProtocol):
    def retrieve(self, query: str) -> list[Document]:
        # Create trace step
        step = TraceStep(
            component="BM25Retriever",
            operation="retrieve",
            input={"query": query},
        )
        
        # Do work
        from rank_bm25 import BM25Okapi
        results = [...]  # Retrieval logic
        
        # Record results
        step.output = {
            "count": len(results),
            "first_score": results[0].metadata.get("score") if results else None,
        }
        step.status = "success"
        
        # Emit to trace
        Trace.add_step(step)
        
        return results
```

**Benefits**:
- Full audit trail of what happened
- Performance monitoring
- Debugging complex pipelines
- Security logging (what was retrieved?)

---

## Pattern Library — Reusable Solutions

### Pattern 1: Implementing a Retriever

**Use this when**: Adding a new retrieval algorithm.

**Files to create**:
1. `adapters/search/<name>_retriever.py` (implementation)
2. `tests/unit/adapters/search/test_<name>_retriever.py` (unit tests)
3. `tests/contract/test_<name>_retriever_conformance.py` (contract tests)

**Step-by-step**:

```python
# Step 1: Import Protocol
from modular_rag.contracts.retrieval import RetrieverProtocol
from modular_rag.core.models.document import Document
from modular_rag.core.observability import Trace, TraceStep

# Step 2: Create Config (Pydantic BaseModel)
from pydantic import BaseModel, Field

class MyRetrieverConfig(BaseModel):
    param1: str = Field(..., description="Description")
    param2: int = Field(default=5, ge=1)

# Step 3: Implement Protocol
class MyRetriever(RetrieverProtocol):
    def __init__(self, config: MyRetrieverConfig):
        self.config = config
    
    def retrieve(self, query: str) -> list[Document]:
        # Lazy import if external library
        from my_library import search_function
        
        # Trace it
        step = TraceStep(component="MyRetriever", operation="retrieve")
        
        # Do work
        results = search_function(query)
        
        # Emit trace
        step.output = {"count": len(results)}
        Trace.add_step(step)
        
        return [Document(id=r.id, text=r.text, ...) for r in results]

# Step 4: Register in registry.py
COMPONENT_REGISTRY["my_retriever"] = MyRetriever

# Step 5: Use in YAML
# manifests/presets/my-preset.yaml:
# components:
#   retriever:
#     type: "my_retriever"
#     config:
#       param1: "value1"
#       param2: 10
```

---

### Pattern 2: Implementing a Security Guard

**Use this when**: Adding input validation, PII redaction, or safety checks.

```python
from modular_rag.contracts.security import SecurityGuardProtocol
from modular_rag.core.observability import Trace, TraceStep

class MyGuard(SecurityGuardProtocol):
    def check(self, text: str) -> tuple[bool, dict]:
        """
        Args:
            text: Input to check
        
        Returns:
            (is_safe, metadata) where:
            - is_safe: bool
            - metadata: {"reason": str, "risk_score": float}
        """
        step = TraceStep(component="MyGuard", operation="check")
        
        # Your logic
        risk_score = 0.0  # 0.0 = safe, 1.0 = blocked
        reason = "OK"
        
        is_safe = risk_score < 0.8
        
        step.output = {
            "is_safe": is_safe,
            "risk_score": risk_score,
        }
        Trace.add_step(step)
        
        return is_safe, {"reason": reason, "risk_score": risk_score}
```

**Key distinction**:
- `safety/filters/` — Injection, toxicity, harmful content
- `safety/redaction/` — PII removal
- `policies/` — Access control, governance (V2+)

---

### Pattern 3: Implementing a Generator

**Use this when**: Adding a new LLM or prompt-based generation.

```python
from modular_rag.contracts.generation import GeneratorProtocol
from modular_rag.core.observability import Trace, TraceStep

class MyGenerator(GeneratorProtocol):
    def __init__(self, config: GeneratorConfig):
        self.config = config
    
    def generate(self, context: str, query: str) -> str:
        # Lazy import for LLM
        from openai import OpenAI  # or anthropic, cohere, etc.
        
        step = TraceStep(component="MyGenerator", operation="generate")
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
Context: {context}
Question: {query}
Answer: """
        
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.temperature,
        )
        
        answer = response.choices[0].message.content
        
        step.output = {
            "tokens_used": response.usage.total_tokens,
            "model": self.config.model,
        }
        Trace.add_step(step)
        
        return answer
```

---

### Pattern 4: Implementing Evaluation Metrics

**Use this when**: Adding scoring/evaluation logic.

```python
from modular_rag.contracts.evaluation import MetricProtocol

class MyMetric(MetricProtocol):
    def compute(
        self,
        predicted: str,
        reference: str,
        **kwargs
    ) -> float:
        """
        Compute metric score [0, 1].
        
        Args:
            predicted: Model output
            reference: Ground truth
            **kwargs: Additional context
        
        Returns:
            score: float in [0.0, 1.0]
        """
        # Your computation
        score = ...
        return score
```

**Register in eval/metrics/__init__.py**:
```python
from eval.metrics.my_metric import MyMetric

ALL_METRICS = {
    "my_metric": MyMetric,
}
```

---

## Real-World Examples

### Example 1: Add BM25 Retriever (Complete)

**Scenario**: Add BM25 lexical search to hybrid pipeline.

#### Step 1: Ask Claude to Explore

```
Prompt:
"Show me how VectorRetriever is structured in 
src/modular_rag/retrieval/vector_retriever.py.
I need to understand:
1. How it implements RetrieverProtocol
2. How it emits TraceSteps
3. Where rank-bm25 should be imported (lazy)
4. How tests are structured"

Claude output:
[Shows code snippets, patterns, dependencies]
```

#### Step 2: Ask Claude to Generate Implementation

```
Prompt:
"Implement BM25Retriever with:
- Location: adapters/search/bm25_retriever.py
- Protocol: RetrieverProtocol
- Config: BM25Config with corpus_path, index_path, k
- Method: retrieve(query: str) -> list[Document]
- Lazy imports for rank-bm25
- Trace emission for observability
- Docstrings explaining why, not what
- Type hints on all parameters

Follow the pattern from VectorRetriever but adapted for BM25.
Include full implementation, not pseudo-code."

Claude output:
[Complete, runnable code]
```

#### Step 3: Ask Claude to Generate Tests

```
Prompt:
"Generate unit tests for BM25Retriever in 
tests/unit/adapters/search/test_bm25_retriever.py:

Test cases:
1. test_initializes_with_valid_config
2. test_retrieve_returns_documents_list
3. test_retrieve_respects_k_parameter
4. test_retrieve_emits_trace_step
5. test_handles_empty_corpus

Use pytest fixtures for setup.
Mock rank-bm25 to avoid installation in unit tests."

Claude output:
[Complete test suite]
```

#### Step 4: Validate

```bash
# Quick check
./scripts/check.sh quick

# If passes:
./scripts/check.sh full

# Review output for:
# ✓ Ruff linting (0 errors)
# ✓ Unit tests (5/5 passing)
# ✓ Contract tests (Protocol conformance passing)
```

#### Step 5: Commit

```bash
git add adapters/search/bm25_retriever.py
git add tests/unit/adapters/search/test_bm25_retriever.py
git add tests/contract/test_bm25_retriever_conformance.py

git commit -m "feat: Add BM25 retriever adapter for lexical search

Implements BM25Okapi lexical retrieval following RetrieverProtocol.
- Adapters/search/bm25_retriever.py with lazy rank-bm25 import
- Full trace emission for observability
- Config-driven corpus and index paths
- Unit tests + contract conformance test

Benefits:
- Hybrid search combining vector + lexical scoring
- Fast development cycle via RRF fusion
- Production-ready with full observability"
```

---

### Example 2: Add PII Redaction Guard

**Scenario**: Add custom PII pattern (credit card numbers).

#### Structure

```
src/modular_rag/security/redaction/patterns/
├── __init__.py
├── pii_detector.py (existing)
└── credit_card_detector.py (NEW)

tests/unit/security/redaction/
├── __init__.py
└── test_credit_card_detector.py (NEW)
```

#### Implementation

```python
# security/redaction/patterns/credit_card_detector.py

import re
from modular_rag.contracts.security import PiiPatternProtocol

class CreditCardDetector(PiiPatternProtocol):
    """Detect credit card numbers (16-digit sequences)."""
    
    # Luhn algorithm check for valid credit cards
    PATTERN = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
    
    def detect(self, text: str) -> list[dict]:
        """
        Find credit card numbers in text.
        
        Returns:
            List of {'start': int, 'end': int, 'text': str}
        """
        matches = []
        for match in self.PATTERN.finditer(text):
            card_text = match.group().replace(' ', '').replace('-', '')
            if self._is_valid_card(card_text):
                matches.append({
                    'start': match.start(),
                    'end': match.end(),
                    'text': match.group(),
                    'type': 'CREDIT_CARD',
                })
        return matches
    
    def _is_valid_card(self, card: str) -> bool:
        """Validate using Luhn algorithm."""
        if not card.isdigit() or len(card) < 13:
            return False
        
        digits = [int(d) for d in card]
        # Luhn check...
        return True  # Simplified
```

#### Tests

```python
# tests/unit/security/redaction/test_credit_card_detector.py

import pytest
from modular_rag.security.redaction.patterns.credit_card_detector import (
    CreditCardDetector,
)

@pytest.fixture
def detector():
    return CreditCardDetector()

def test_detects_visa(detector):
    text = "Pay with 4532-1234-5678-9010"
    matches = detector.detect(text)
    assert len(matches) == 1
    assert matches[0]['type'] == 'CREDIT_CARD'

def test_ignores_short_numbers(detector):
    text = "My ID is 123456"
    matches = detector.detect(text)
    assert len(matches) == 0

def test_detects_multiple(detector):
    text = "Use 4532123456789010 or 5105105105105100"
    matches = detector.detect(text)
    assert len(matches) == 2
```

#### Registration

```python
# security/redaction/__init__.py

from security.redaction.patterns.credit_card_detector import CreditCardDetector

PII_DETECTORS = {
    "pii": PiiDetector(),
    "credit_card": CreditCardDetector(),
    # ...
}
```

#### Usage

```yaml
# manifests/presets/secure-rag.yaml

security:
  redaction:
    detectors:
      - type: "credit_card"
        replace_with: "[REDACTED_CARD]"
```

---

## Validation & Testing

### Test Scopes & When to Use

| Scope | Command | When to Use | Time | Requires |
|-------|---------|------------|------|----------|
| **Unit** | `pytest tests/unit/` | After every code change | 30s-1m | Nothing |
| **Contract** | `pytest tests/contract/` | After Protocol implementation | 1m | Nothing |
| **Integration** | `pytest tests/integration/ -m integration` | With external services | 2-5m | Qdrant on :6333 |
| **E2E** | `pytest tests/e2e/ -m e2e` | Full pipeline validation | 5-10m | Qdrant + LLM API key |
| **All** | `./scripts/check.sh all` | Pre-release, CI/CD | 10-15m | Everything |

### Testing Checklist

**For every new component**:

```
☑ Unit test file created: tests/unit/<path>/test_<name>.py
☑ At least 3 test cases (happy path + edge cases)
☑ Contract test created: tests/contract/test_<name>_conformance.py
☑ Protocol methods tested
☑ Trace emission verified
☑ Lazy imports tested (verify not imported at module level)
☑ Type hints verified (mypy passes)
☑ Coverage > 80%
```

**Command to verify coverage**:

```bash
pytest tests/unit/ tests/contract/ --cov=src/modular_rag --cov-report=term-missing
```

---

## Debugging & Troubleshooting

### Common Error: Import Violations

**Error**:
```
ImportError: cannot import name 'BM25Retriever' from 'retrieval'
```

**Root Cause**: Trying to import from domain module in another domain module.

**Diagnosis**:

```bash
# Find the import
grep -r "from retrieval import" src/modular_rag/

# Likely culprit:
# src/modular_rag/generation/my_generator.py:
#   from retrieval.bm25_retriever import BM25Retriever  # ✗ WRONG
```

**Fix**:

```
Option A: If you need shared logic
→ Move to contracts/retrieval.py as a Protocol method
→ Both modules implement and use the shared Protocol

Option B: If in adapter
→ Import in adapters/, not in domain module

Option C: If in orchestration
→ Use registry pattern + YAML config, not direct import

Option D: If in tests
→ That's OK, tests can import anything for verification
```

---

### Common Error: Protocol Not Implemented

**Error**:
```
TypeError: Can't instantiate abstract class MyRetriever 
with abstract methods retrieve, batch_retrieve
```

**Root Cause**: Missing methods from Protocol.

**Diagnosis**:

```python
from modular_rag.contracts.retrieval import RetrieverProtocol
import inspect

# Show all Protocol methods
print(inspect.getmembers(RetrieverProtocol, predicate=inspect.ismethod))

# Check what MyRetriever has
from my_module import MyRetriever
my_methods = [m for m in dir(MyRetriever) if not m.startswith('_')]
print(my_methods)

# Compare and find missing methods
```

**Fix**:

```python
class MyRetriever(RetrieverProtocol):
    # Add missing methods
    def batch_retrieve(self, queries: list[str]) -> list[list[Document]]:
        return [self.retrieve(q) for q in queries]
```

---

### Common Error: Trace Not Emitted

**Error**:
```
AssertionError: Trace has 0 steps, expected > 0
```

**Root Cause**: Forgot to emit TraceStep.

**Diagnosis**:

```python
# Check if TraceStep is emitted
def retrieve(self, query: str) -> list[Document]:
    # Missing: step = TraceStep(...)
    results = [...]
    # Missing: Trace.add_step(step)
    return results
```

**Fix**:

```python
from modular_rag.core.observability import Trace, TraceStep

def retrieve(self, query: str) -> list[Document]:
    step = TraceStep(component="MyRetriever", operation="retrieve")
    
    results = [...]
    
    step.output = {"count": len(results)}
    Trace.add_step(step)  # ✓ Add this
    
    return results
```

---

### Common Error: Type Hints Incomplete

**Error**:
```
error: Argument 1 to "MyClass" has incompatible type "str"; 
expected "Document"  [arg-type]
```

**Root Cause**: Missing or incorrect type hints.

**Fix**:

```python
# ❌ WRONG
def process(item):
    return item.text

# ✅ CORRECT
from modular_rag.core.models.document import Document

def process(item: Document) -> str:
    return item.text
```

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Hard-Coded Dependencies

```python
# ❌ WRONG
class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Retriever()  # Hard-coded
        self.vector = VectorRetriever()  # Hard-coded

# ✅ CORRECT
class HybridRetriever:
    def __init__(self, bm25: RetrieverProtocol, vector: RetrieverProtocol):
        self.bm25 = bm25  # Injected
        self.vector = vector  # Injected
```

---

### ❌ Anti-Pattern 2: Module-Level Heavy Imports

```python
# ❌ WRONG
from rank_bm25 import BM25Okapi  # At top level!
from sentence_transformers import SentenceTransformer

class BM25Retriever:
    def retrieve(self, query: str):
        ...

# ✅ CORRECT
class BM25Retriever:
    def retrieve(self, query: str):
        from rank_bm25 import BM25Okapi  # Inside method!
        ...
```

---

### ❌ Anti-Pattern 3: Cross-Domain Imports

```python
# ❌ WRONG in retrieval/
from generation.openai_generator import OpenAIGenerator
from security.pii_guard import PiiGuard

# ✅ CORRECT
from contracts.retrieval import RetrieverProtocol
from core.models.document import Document
```

---

### ❌ Anti-Pattern 4: No Trace Emission

```python
# ❌ WRONG
def retrieve(self, query: str) -> list[Document]:
    results = self.index.search(query)
    return results  # Lost all context!

# ✅ CORRECT
def retrieve(self, query: str) -> list[Document]:
    step = TraceStep(component="MyRetriever", operation="retrieve")
    
    results = self.index.search(query)
    
    step.output = {"count": len(results), "query": query}
    Trace.add_step(step)  # Audit trail!
    
    return results
```

---

### ❌ Anti-Pattern 5: Magic Numbers and Strings

```python
# ❌ WRONG
class MyRetriever:
    def retrieve(self, query):
        results = self.index.search(query, top_k=5)  # Magic 5!
        if len(results) == 0:
            return []
        return results[:5]  # Magic 5 again!

# ✅ CORRECT
from pydantic import BaseModel, Field

class MyRetrieverConfig(BaseModel):
    k: int = Field(default=5, ge=1, description="Number of results")

class MyRetriever:
    def __init__(self, config: MyRetrieverConfig):
        self.config = config
    
    def retrieve(self, query: str) -> list[Document]:
        results = self.index.search(query, top_k=self.config.k)
        return results[:self.config.k]  # Config-driven!
```

---

## Quick Reference Card

### Commands Cheat Sheet

```bash
# Daily Development
./scripts/check.sh quick        # 30s - syntax check
./scripts/check.sh full         # 2-5m - before commit

# Debugging
pytest tests/unit/path/to/test.py -v  # Single test
pytest -k "test_name" -v              # By pattern
pytest --pdb                           # Debug mode

# CI/CD
./scripts/check.sh all          # 10-15m - pre-release

# Git
git status
git add src/modular_rag/...
git commit -m "feat: Description"
git push origin feature/name
```

### Architecture Checklist

```
Before writing code:
☑ Which layer? (domain, adapter, orchestration, etc.)
☑ Does a Protocol exist? (check contracts/)
☑ Can I import this? (check layering rules)
☑ Is it external? (lazy import required)
☑ Need to trace? (emit TraceStep)
☑ Where are tests? (unit + contract)

After writing code:
☑ ./scripts/check.sh quick passes
☑ ./scripts/check.sh full passes
☑ Type hints on all parameters
☑ Docstrings explain why, not what
☑ Tests cover happy path + edge cases
☑ Trace step emitted for observability
☑ No cross-domain imports
☑ Lazy imports for external libs
```

### File Templates

**New Retriever**:
```
adapters/search/<name>_retriever.py
├── Import Protocol
├── Define Config (Pydantic)
├── Implement class (Protocol methods)
├── Lazy imports (inside methods)
├── Trace emissions
└── Register in orchestration/registry.py

tests/unit/adapters/search/test_<name>_retriever.py
├── Fixtures (config, mock data)
├── Test initialization
├── Test retrieve() return type
├── Test config parameters
└── Test trace emission

tests/contract/test_<name>_retriever_conformance.py
├── Import Protocol
├── Verify all methods exist
├── Verify method signatures
└── Verify Protocol contract holds
```

---

## Summary

**The Complete Workflow**:

1. **EXPLORE** (5-15 min) — Understand problem, read docs, clarify requirements
2. **PLAN** (10-15 min) — Choose architecture, plan dependencies, design API
3. **IMPLEMENT** (30-45 min) — Generate code, write tests, follow patterns
4. **VERIFY** (5-15 min) — Run checks, ensure all tests pass
5. **DELIVER** (15-30 min) — Self-check, address feedback, commit

**Golden Rules**:
- ✅ Hexagonal layering (one-directional dependencies)
- ✅ Lazy imports (heavy libraries inside methods)
- ✅ Wire via registry + YAML (no Python wiring)
- ✅ Emit TraceSteps (observability)
- ✅ Follow patterns (reusable solutions)
- ✅ Test everything (unit + contract + integration)
- ✅ Type hints everywhere (mypy pass)
- ✅ Never cross-domain (retrieval ≠ generation)

**Next Steps**:
1. Read [CLAUDE-CODE-COMPLETE-GUIDE.md](./CLAUDE-CODE-COMPLETE-GUIDE.md)
2. Review [docs/architecture/overview.md](../architecture/overview.md)
3. Check [docs/adr/](../adr/) for relevant decisions
4. Start with `/quick-check` command to validate your environment
5. Implement your first feature following this guide
