# CLAUDE.md — Orchestration Module

This file provides guidance for Claude working on the orchestration (registry, engine, wiring) layer. Read this **before editing any file in this directory**.

---

## ⚠️ Central Nervous System

The orchestration module is the **framework's central hub**:
- `registry.py` — Component lifecycle and dependency injection
- `engine.py` — RAG pipeline execution with TraceStep emissions
- `router.py` — Query routing and fallback logic
- `compiler.py` — State machine compilation
- `config.py` — Configuration and schema validation

**Changes here affect every workflow, retriever, generator, and agent.**

---

## Rule 1: Registry Pattern — Manifest-Driven Wiring

### NEVER Wire Components in Python

### ❌ FORBIDDEN

```python
# ❌ Direct Python instantiation (breaks manifest-driven architecture)
from modular_rag.ingestion.chunkers.fixed import FixedChunker
from modular_rag.retrieval.bm25 import BM25Retriever

chunker = FixedChunker(chunk_size=512)
retriever = BM25Retriever(chunker=chunker, k=10)
```

### ✅ ALLOWED

```python
# ✅ Manifest-driven via registry
import yaml
from modular_rag.orchestration.registry import ComponentRegistry

# Load config
with open("manifests/presets/local-hybrid-rag.yaml") as f:
    config = yaml.safe_load(f)

# Wire via registry
registry = ComponentRegistry()
registry.wire(config)

# Get components by name
chunker = registry.get_component("chunker", config.chunker.type)
retriever = registry.get_component("retriever", config.retriever.type)
```

### Why This Matters

- **Manifest-driven**: All configuration lives in YAML, not scattered in Python code
- **Lazy loading**: Components instantiated only when needed
- **Testability**: Easy to swap implementations for testing
- **Extensibility**: New components added without modifying Python code

---

## Rule 2: ComponentRegistry — Interface and Responsibilities

### Registry Methods

```python
class ComponentRegistry:
    """Manages component lifecycle and dependency injection."""
    
    def register(
        self,
        category: str,
        name: str,
        factory: Callable[[Config], Any]
    ) -> None:
        """Register a component factory.
        
        Args:
            category: Component type (e.g., "retriever", "embedder")
            name: Component name (e.g., "bm25", "openai")
            factory: Callable that creates component instance
        """
        ...
    
    def get_component(self, category: str, name: str) -> Any:
        """Get registered component by name."""
        ...
    
    def wire(self, config: RAGConfig) -> None:
        """Wire all components from manifest config.
        
        This is the main entry point. It orchestrates component creation,
        dependency injection, and initialization.
        """
        ...
```

### Registering Components

**Location**: `orchestration/_default_factories.py`

```python
def register_default_factories(registry: ComponentRegistry):
    """Register all built-in components."""
    
    # Chunkers
    registry.register(
        "chunker",
        "fixed",
        lambda cfg: FixedChunker(
            chunk_size=cfg.config.get("chunk_size", 512),
            overlap=cfg.config.get("overlap", 0)
        )
    )
    
    # Retrievers
    registry.register(
        "retriever",
        "bm25",
        lambda cfg: BM25Retriever(
            k=cfg.config.get("k", 10),
            corpus=cfg.config.get("corpus", [])
        )
    )
```

### Never Register Here

- ❌ Do NOT register in domain modules (ingestion/, retrieval/, etc.)
- ❌ Do NOT register in adapters (they're lazy-loaded)
- ✅ Register ONLY in `_default_factories.py`

---

## Rule 3: RAGEngine — Pipeline Execution with TraceStep

### Engine Responsibilities

```python
class RAGEngine:
    """Orchestrates RAG pipeline execution.
    
    Flow:
    1. Parse query (security guards)
    2. Route query (RouterDecision)
    3. Retrieve documents (retriever)
    4. Rerank if needed (reranker)
    5. Generate answer (generator)
    6. Guard output (security guards)
    7. Emit trace
    """
    
    def run(self, request: QueryRequest) -> QueryResponse:
        """Execute full RAG pipeline.
        
        Args:
            request: User query + metadata
            
        Returns:
            response: Generated answer + metadata + trace
            
        Raises:
            SecurityError: If query/answer blocked by guards
            ComponentError: If pipeline component fails
        """
        ...
```

### TraceStep Emissions (MANDATORY)

Every major operation must emit a `TraceStep`:

```python
from modular_rag.observability import Trace

def run(self, request: QueryRequest) -> QueryResponse:
    trace = Trace()
    
    # STEP 1: Parse and guard query
    trace.add_step(
        operation="parse_query",
        status="started",
        input=request.query,
        model="clause_extractor_v1"
    )
    
    try:
        parsed = self.parse_query(request)
        trace.add_step(
            operation="parse_query",
            status="completed",
            output={"entities": parsed.entities},
        )
    except Exception as e:
        trace.add_step(
            operation="parse_query",
            status="failed",
            error=str(e)
        )
        raise
    
    # STEP 2: Retrieve
    trace.add_step(operation="retrieve", status="started")
    docs = self.retriever.retrieve(parsed.query)
    trace.add_step(
        operation="retrieve",
        status="completed",
        output={"doc_count": len(docs)}
    )
    
    # STEP 3: Generate
    trace.add_step(operation="generate", status="started")
    answer = self.generator.generate(parsed, docs)
    trace.add_step(
        operation="generate",
        status="completed",
        output={"answer_length": len(answer)}
    )
    
    return QueryResponse(
        answer=answer,
        trace=trace
    )
```

### When to Emit TraceStep

- ✅ Query parsing (parsing guards, routing decisions)
- ✅ Retrieval (number of docs, scores)
- ✅ Reranking (rerank scores, final order)
- ✅ Generation (model used, tokens, latency)
- ✅ Output guards (any blocking/filtering)
- ❌ NEVER: Full query text if contains PII
- ❌ NEVER: Full answer text if contains secrets

---

## Rule 4: QueryRouter — Decision Logic

### Router Responsibilities

```python
class QueryRouter:
    """Routes queries to appropriate retrieval strategy."""
    
    def route(self, query: str) -> RouterDecision:
        """Determine retrieval strategy.
        
        Returns:
            decision: {
                "strategy": "hybrid" | "vector" | "lexical" | "fallback",
                "confidence": 0.0-1.0,
                "reason": "explanation for decision"
            }
        """
        ...
```

### Routing Strategies

| Strategy | When to Use | Fallback |
|----------|------------|----------|
| **hybrid** | Default; balanced accuracy | vector |
| **vector** | Semantic queries; "find similar" | lexical |
| **lexical** | Keyword queries; entity search | vector |
| **fallback** | Router confidence < 0.5 | return empty results |

### Router Implementation

```python
def route(self, query: str) -> RouterDecision:
    """Route based on query characteristics."""
    
    # Analyze query
    keywords = self.extract_keywords(query)
    entities = self.extract_entities(query)
    semantic_score = self.measure_semantic_content(query)
    
    # Decision logic
    if len(entities) > 0 and semantic_score < 0.3:
        # Entity-heavy query → lexical search good
        return RouterDecision(
            strategy="lexical",
            confidence=0.8,
            reason="Entity-focused query (entities found, low semantic content)"
        )
    
    elif semantic_score > 0.7:
        # Semantic query → vector search
        return RouterDecision(
            strategy="vector",
            confidence=0.8,
            reason="High semantic content; vector search recommended"
        )
    
    else:
        # Default → hybrid (combines both)
        return RouterDecision(
            strategy="hybrid",
            confidence=0.6,
            reason="Mixed semantic/lexical; hybrid recommended"
        )
```

---

## Rule 5: RAGConfig Schema Validation

### Config Structure

```python
@dataclass
class RAGConfig:
    """Root configuration for RAG pipeline.
    
    Loaded from manifest YAML and validated here.
    """
    
    ingestion: IngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    security: SecurityConfig  # optional
    observability: ObservabilityConfig  # optional
    
    def validate(self) -> None:
        """Validate config consistency."""
        # Check all required components registered
        # Check no circular dependencies
        # Check all manifests referenced exist
        ...
```

### Never Allow

- ❌ Circular dependencies (A depends on B, B depends on A)
- ❌ Missing component references (manifest says "retriever: xyz" but xyz not registered)
- ❌ Invalid config types (expecting int, got string)

---

## Rule 6: StateMachine Compilation

### When to Use StateMachine

StateMachine is for **multi-turn workflows** with state transitions (V2+).

```python
class StateMachine:
    """Manages workflow state and transitions.
    
    V2+ feature: multi-turn conversation, decision trees, etc.
    V1: Not used (single-turn RAG).
    """
    
    def compile(self, flow_spec: Dict) -> None:
        """Compile flow specification to state graph."""
        # Convert YAML flow to executable state graph
        ...
    
    def execute(self, input_data: Any) -> Any:
        """Execute state machine."""
        # Process through states, handle transitions
        ...
```

**V1 scope**: Do NOT implement state transitions. Use router for single-shot routing.

---

## Checklist Before Editing

- [ ] Am I adding a new component? Register in `_default_factories.py`?
- [ ] Am I changing engine flow? Added all TraceStep emissions?
- [ ] Am I changing config schema? Updated and validated schema in `config.py`?
- [ ] Am I changing router logic? Added reason and confidence to RouterDecision?
- [ ] Does this change wire components in Python? (❌ NO — use manifest)
- [ ] Does this expose secrets in trace or logs? (❌ NO — check TraceStep content)
- [ ] Is this a state machine change? (✅ OK only if V2+ scope clearly documented)

---

## References

- [ADR-0002: Contracts and Plugins](../../docs/adr/0002-contracts-and-plugins.md)
- [.claude/.instructions.md](../../.claude/.instructions.md) — Registry pattern section
- [.claude/rules/orchestration.md](../../.claude/rules/orchestration.md) — Detailed rules
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Component addition workflow

