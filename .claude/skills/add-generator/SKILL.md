---
name: add-generator
description: Step-by-step workflow for implementing a new LLM generator following the Generator contract
---

# Add Generator Skill

> **Corrected 2026-08-06** (documentation-utility pass): this file previously described a
> fictional `GeneratorProtocol` (`generate(context: str, query: str, **kwargs) -> str`,
> `estimate_tokens()`), a `RagConfig` class, a `TraceStep(component=, method=)` constructor, and
> a `BUILT_IN_GENERATORS` registry dict — none of which exist in the real code. Rewritten below
> against the actual `Generator` protocol (`src/modular_rag/contracts/generation.py`), the real
> `TraceStep`/`Trace` schema (`src/modular_rag/core/models/trace.py`), and the real
> registration pattern (`src/modular_rag/orchestration/_default_factories.py`), using
> `OpenAIGenerator` (`src/modular_rag/generation/synthesizers/openai_gen.py`) as the reference
> implementation.

## State of the Art First (mandatory)

Before designing the generator, read [docs/research/DIGEST-generation.md](../../../docs/research/DIGEST-generation.md) and [docs/research/DIGEST-overviews.md](../../../docs/research/DIGEST-overviews.md) and cite the arXiv id backing each design choice. Key baselines: prompt-based grounding + numbered-source format validated as the correct System-1 baseline; one-citation-per-chunk supported; token-overlap is a lexical-support *gate*, not a faithfulness metric (true faithfulness = supported-statements ratio, RAGAS-style — V1.1); temperature is an engineering default, uncited.

## Parameters (advisory — not schema-validated by Claude Code)

Claude Code skills don't support typed/validated parameters in frontmatter; describe these to the agent in your invocation prompt instead:

- `generator_type` (enum, required) — one of: ['openai', 'anthropic', 'cohere', 'local', 'custom']
- `generator_name` (string, required) — pattern: `^[A-Z][a-zA-Z0-9]*Generator$`
- `model_name` (string, required) — LLM model identifier (e.g., gpt-4o-mini, claude-3-5-sonnet)

_Originally authored as a workflow for `generation-specialist`, invoked as `/add-generator`._

Guided workflow for implementing a new LLM generator against the `Generator` contract.

## When to Use

- Adding support for new LLM provider (OpenAI, Anthropic, Cohere)
- Implementing specialized generators (multi-stage, ensemble)
- Integrating local models
- Optimizing generation for specific use cases

## Workflow Steps

### 1. Verify Protocol Compliance (5 min)

**Review `Generator` in:** `src/modular_rag/contracts/generation.py`

**Required methods:**
```python
def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer: ...
async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer: ...
def name(self) -> str: ...
```
Every `generate()`/`agenerate()` call must emit a `TraceStep` on the `trace` argument passed in
by the caller — generators never own or construct their own `Trace`.

### 2. Create Implementation File (10 min)

**File:** `src/modular_rag/generation/synthesizers/{generator_name}.py` (the existing generators
live in `generation/synthesizers/`, not directly under `generation/`)

```python
from __future__ import annotations

import time

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.generation.citations.builder import build_citations
from modular_rag.generation.validators.groundedness import GroundednessValidator


class {GeneratorName}:
    """{{Description}}"""

    def __init__(
        self,
        model: str = "{model_name}",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self._client: object | None = None
        self._groundedness = GroundednessValidator()

    def name(self) -> str:
        return "{generator_name}"

    def _get_client(self) -> object:
        if self._client is None:
            # Lazy import — heavy SDK stays out of module-level imports
            from some_llm_sdk import Client

            self._client = Client(api_key=self.api_key or None, timeout=self.timeout)
        return self._client

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        parts = []
        for i, rc in enumerate(chunks, 1):
            source = rc.chunk.metadata.get("source", "unknown")
            parts.append(f"[{i}] Source: {source}\n{rc.chunk.content}")
        return "\n\n".join(parts)

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        client = self._get_client()
        ctx_text = self._build_context(context)

        t0 = time.perf_counter()
        response = client.complete(  # type: ignore[attr-defined]
            prompt=f"Context:\n{ctx_text}\n\nQuestion: {query.text}",
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        trace.add_step(TraceStep(
            name="{generator_name}_generate",
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            latency_ms=latency_ms,
            metadata={"model": self.model},
        ))

        citations = build_citations(context)
        answer = Answer(query_id=query.id, text=response.text, citations=citations, model=self.model)
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)  # override with a real async client call if the SDK supports it

    def close(self) -> None:
        """Release the underlying client, if one was ever opened (Lot 14 pattern —
        own and close clients/resources)."""
        if self._client is not None:
            self._client.close()  # type: ignore[attr-defined]
            self._client = None
```

### 3. Implement Prompt Templates (15 min)

**System prompt pattern** (see `openai_gen.py`'s `_SYSTEM_PROMPT` for the reference,
research-cited version — instruct the model to cite sources and refuse when context is
insufficient):
```python
_SYSTEM_PROMPT = """\
You are a precise assistant. Answer the user's question using ONLY the provided context.
Cite the source of each claim. If the context is insufficient, say so explicitly.
If the context does not contain the answer, say you don't know — do not guess.
"""
```

### 4. Handle Multi-Model Support (10 min)

If the generator needs to route between several models, branch inside `_get_client()`/`generate()`
rather than adding a second Protocol — `Generator` has no `model` parameter on `generate()`
itself; model selection is a constructor-time concern (`self.model`), consistent with
`OpenAIGenerator` and `AnthropicGenerator`.

### 5. Create Unit Tests (20 min)

**File:** `tests/unit/generation/synthesizers/test_{generator_name}.py`

```python
import pytest

from modular_rag.core.models.query import Query
from modular_rag.core.models.trace import Trace
from modular_rag.generation.synthesizers.{generator_name} import {GeneratorName}


class Test{GeneratorName}:

    @pytest.fixture
    def generator(self):
        return {GeneratorName}(api_key="test-key")

    def test_generate_success(self, generator, monkeypatch):
        # Mock the lazily-imported client so the test needs no network access
        ...
        query = Query(text="What is RAG?")
        trace = Trace(query_id=query.id)
        answer = generator.generate(query, context=[], trace=trace)
        assert answer.text
        assert len(trace.steps) == 1

    def test_name_returns_registered_type(self, generator):
        assert generator.name() == "{generator_name}"
```

### 6. Create Contract Conformance Test (10 min)

**File:** `tests/contract/test_generator_conformance.py` (add a case to the existing file — see
that file for the pattern of asserting `isinstance(instance, Generator)`)

```python
from modular_rag.contracts.generation import Generator
from modular_rag.generation.synthesizers.{generator_name} import {GeneratorName}


def test_{generator_name}_conforms_to_generator_protocol():
    instance = {GeneratorName}(api_key="test-key")
    assert isinstance(instance, Generator)
```

### 7. Register in Registry (5 min)

**File:** `src/modular_rag/orchestration/_default_factories.py` — add the import inside
`register_defaults()` (all component imports there are function-local) and one `reg.register(...)`
line, following the existing generator entries:

```python
from modular_rag.generation.synthesizers.{generator_name} import {GeneratorName}
...
reg.register("generator", "{generator_name}", lambda cfg: {GeneratorName}(**cfg.config))
```

### 8. Create Manifest Example (5 min)

```yaml
generation:
  generator:
    type: "{generator_name}"
    config:
      model: "{model_name}"
      temperature: 0.1
      max_tokens: 2048
      api_key: "..."   # manifests do NOT support ${VAR} interpolation (see manifests/README.md)
                        # — pass the key directly, or leave it unset and rely on the SDK's own
                        # standard env var (e.g. OPENAI_API_KEY), never a custom MRAG_* var
```

### 9. Validate & Test (5 min)

```bash
# Unit tests
pytest tests/unit/generation/synthesizers/test_{generator_name}.py -v

# Contract tests
pytest tests/contract/test_generator_conformance.py -v

# Full check
./scripts/check.sh full
```

## Success Criteria

✅ `Generator` protocol fully implemented (`generate`, `agenerate`, `name`)
✅ Lazy imports on LLM libraries
✅ Prompt templates working
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ TraceStep emitted on every `generate()`/`agenerate()` call
✅ Registered in `_default_factories.py`, selected by name in a manifest

## Time Estimate

**Total:** 1.5-2 hours
