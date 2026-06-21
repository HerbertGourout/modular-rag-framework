---
name: add-generator
shortDescription: Add a new generator implementation to the framework
description: Step-by-step workflow for implementing a new LLM generator following GeneratorProtocol
author: generation-specialist
invocation: /add-generator
parameters:
  - name: generator_type
    type: enum
    values: [openai, anthropic, cohere, local, custom]
    required: true
  - name: generator_name
    type: string
    pattern: "^[A-Z][a-zA-Z0-9]*Generator$"
    required: true
  - name: model_name
    type: string
    description: "LLM model identifier (e.g., gpt-4, claude-2)"
    required: true
---

# Add Generator Skill

Guided workflow for implementing a new LLM generator following GeneratorProtocol.

## When to Use

- Adding support for new LLM provider (GPT-4, Claude, Cohere)
- Implementing specialized generators (multi-stage, ensemble)
- Integrating local models
- Optimizing generation for specific use cases

## Workflow Steps

### 1. Verify Protocol Compliance (5 min)

**Review `GeneratorProtocol` in:** `src/modular_rag/contracts/generation.py`

**Required methods:**
- `generate(context: str, query: str, **kwargs) → str`
- `estimate_tokens(text: str) → int`
- All methods must emit `TraceStep`

### 2. Create Implementation File (10 min)

**File:** `src/modular_rag/generation/{generator_name}.py`

```python
from modular_rag.contracts.generation import GeneratorProtocol
from modular_rag.core.trace import Trace, TraceStep
from modular_rag.core.models import RagConfig
from typing import Optional

class {GeneratorName}(GeneratorProtocol):
    """{{Description}}"""
    
    def __init__(self, config: RagConfig, **kwargs):
        self.config = config
        self.model_name = "{model_name}"
        # Lazy import external library
        
    def generate(
        self, 
        context: str, 
        query: str, 
        **kwargs
    ) -> str:
        """Generate answer from context and query."""
        step = TraceStep(
            component=self.__class__.__name__,
            method="generate"
        )
        
        try:
            # 1. Build prompt
            prompt = self._build_prompt(context, query)
            
            # 2. Call LLM (lazy import)
            from external_lib import LLMClient
            client = LLMClient(self.config.get("api_key"))
            
            response = client.complete(
                prompt=prompt,
                model=self.model_name,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 500)
            )
            
            # 3. Extract and validate
            answer = response.text
            
            # 4. Track metrics
            step.metadata = {
                "input_tokens": self.estimate_tokens(prompt),
                "output_tokens": self.estimate_tokens(answer),
                "model": self.model_name,
                "temperature": kwargs.get("temperature", 0.7)
            }
            
            return answer
            
        except Exception as e:
            step.status = "error"
            step.error = str(e)
            raise
        finally:
            Trace.add_step(step)
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count."""
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
    
    def _build_prompt(self, context: str, query: str) -> str:
        """Build prompt from context and query."""
        return f"""Using the provided context, answer the question.

Context:
{context}

Question: {query}

Answer:"""
```

### 3. Implement Prompt Templates (15 min)

**Pattern for dynamic prompts:**
```python
def _build_prompt(self, context: str, query: str) -> str:
    system_prompt = """You are a helpful assistant answering questions based on provided context.
    Be accurate, concise, and cite sources from the context."""
    
    # Simple template
    user_prompt = f"""Context:
{context}

Question: {query}

Answer:"""
    
    return f"{system_prompt}\n\n{user_prompt}"
```

**Pattern for few-shot learning:**
```python
def _build_prompt_with_examples(self, context: str, query: str) -> str:
    examples = [
        {
            "context": "RAG (Retrieval-Augmented Generation) combines retrieval and generation.",
            "query": "What is RAG?",
            "answer": "RAG is a technique that combines retrieval and generation to provide accurate answers."
        }
    ]
    
    prompt = "Answer the question based on context.\n\n"
    
    for ex in examples:
        prompt += f"Context: {ex['context']}\nQuestion: {ex['query']}\nAnswer: {ex['answer']}\n\n"
    
    prompt += f"Context: {context}\nQuestion: {query}\nAnswer:"
    
    return prompt
```

### 4. Handle Multi-Model Support (10 min)

**Pattern for multiple models:**
```python
class UnifiedGenerator(GeneratorProtocol):
    """Support multiple LLM models."""
    
    SUPPORTED_MODELS = {
        "gpt-4": {"max_tokens": 8192, "cost_per_1k": 0.03},
        "gpt-3.5": {"max_tokens": 4096, "cost_per_1k": 0.001},
        "claude-2": {"max_tokens": 100000, "cost_per_1k": 0.008},
    }
    
    def generate(self, context: str, query: str, **kwargs) -> str:
        model = kwargs.get("model", self.model_name)
        
        if model == "gpt-4":
            return self._generate_with_openai(context, query, model)
        elif model == "claude-2":
            return self._generate_with_anthropic(context, query, model)
        else:
            raise ValueError(f"Unsupported model: {model}")
```

### 5. Create Unit Tests (20 min)

**File:** `tests/unit/generation/test_{generator_name}.py`

```python
import pytest
from modular_rag.generation.{generator_name} import {GeneratorName}
from modular_rag.core.models import RagConfig

class Test{GeneratorName}:
    
    @pytest.fixture
    def generator(self):
        config = RagConfig(api_key="test-key")
        return {GeneratorName}(config)
    
    def test_generate_success(self, generator):
        context = "RAG combines retrieval and generation."
        query = "What is RAG?"
        
        answer = generator.generate(context, query)
        
        assert isinstance(answer, str)
        assert len(answer) > 0
    
    def test_token_estimation(self, generator):
        text = "This is a test text with some words."
        tokens = generator.estimate_tokens(text)
        
        assert tokens > 0
        assert isinstance(tokens, int)
    
    def test_prompt_building(self, generator):
        context = "Test context"
        query = "Test query"
        
        prompt = generator._build_prompt(context, query)
        
        assert "Test context" in prompt
        assert "Test query" in prompt
```

### 6. Create Contract Conformance Test (10 min)

**File:** `tests/contract/test_{generator_name}_conformance.py`

```python
from modular_rag.generation.{generator_name} import {GeneratorName}
from modular_rag.contracts.generation import GeneratorProtocol

def test_protocol_implementation():
    """Verify {GeneratorName} implements GeneratorProtocol."""
    assert issubclass({GeneratorName}, GeneratorProtocol)
    assert hasattr({GeneratorName}, 'generate')
    assert hasattr({GeneratorName}, 'estimate_tokens')

def test_generate_returns_string(generator):
    """Verify generate() returns str."""
    result = generator.generate("context", "query")
    assert isinstance(result, str)
```

### 7. Register in Registry (5 min)

**File:** `src/modular_rag/orchestration/registry.py`

```python
from modular_rag.generation.{generator_name} import {GeneratorName}

def _create_{generator_name}(config: dict) -> GeneratorProtocol:
    """Factory for {GeneratorName}."""
    return {GeneratorName}(config)

BUILT_IN_GENERATORS = {
    # ... existing generators
    "{generator_name}": _create_{generator_name},
}
```

### 8. Create Manifest Example (5 min)

```yaml
generation:
  generator:
    type: {generator_name}
    model: {model_name}
    temperature: 0.7
    max_tokens: 500
    api_key: ${MRAG_API_KEY}
```

### 9. Validate & Test (5 min)

```bash
# Unit tests
pytest tests/unit/generation/test_{generator_name}.py -v

# Contract tests
pytest tests/contract/test_{generator_name}_conformance.py -v

# Full check
./scripts/check.sh full
```

## Success Criteria

✅ GeneratorProtocol fully implemented
✅ Lazy imports on LLM libraries
✅ Prompt templates working
✅ Token estimation accurate (within 10%)
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ Error handling for API failures
✅ TraceStep emission complete
✅ Cost tracking implemented

## Time Estimate

**Total:** 1.5-2 hours
