# Sub-Agents and Parallelization

This guide explains how to use Claude Code's sub-agents to explore complex topics in parallel and isolate context — particularly useful for large tasks that have several independent dimensions.

---

## What Are Sub-Agents?

**Sub-agents** are specialized Claude instances that run in parallel, each focused on a specific aspect of a larger problem. They work independently and return their findings to the main agent, which synthesizes results and makes decisions.

**Why use them?**
- Large monorepos are hard to understand in one go
- Breaking changes need analysis across multiple layers
- Complex refactors involve different modules
- Parallel exploration is faster than sequential

**When NOT to use them?**
- Simple tasks (<30 min)
- Well-understood codebases
- Tasks that depend on prior steps
- Single-module changes

---

## The 4 Sub-Agent Types

### 1. 🗺️ Mapping Sub-Agent

**Purpose**: Explore and list all usages of a module or component in the codebase.

**Useful for**:
- Understanding impact of changes
- Finding all places using a Protocol
- Breaking changes analysis
- "What would break if I rename this?"

**Example task**:

```
Mapping sub-agent: Explore VectorRetriever usage

Search for all usages of VectorRetriever in the codebase:
1. Where is it imported?
2. Where is it instantiated?
3. Where is it referenced in tests?
4. Where is it registered?

Return: List of all files + line numbers
```

**Expected output**:

```
VectorRetriever Usage Map
========================

Imports (9 total):
  - src/modular_rag/retrieval/__init__.py:5 (export)
  - src/modular_rag/orchestration/_default_factories.py:12 (registration)
  - tests/unit/retrieval/test_vector.py:3 (test)
  - tests/contract/test_retrieval_conformance.py:8 (contract test)
  - examples/simple_qa/main.py:15 (example)
  - manifests/ (2 YAML configs)
  - docs/ (1 documentation reference)

Direct Instantiation (3 total):
  - tests/unit/retrieval/test_vector.py:42 (test setup)
  - tests/e2e/test_simple_qa_pipeline.py:18 (e2e test)
  - examples/simple_qa/main.py:25 (example)

Registry Registration (1 total):
  - src/modular_rag/orchestration/_default_factories.py:45

Impact Summary:
  - If renamed: 9 imports + 3 instantiations + 1 registration = 13 changes
  - If signature changed: 3 instantiations + registry pattern = 4 changes
  - If removed: 5 files would break (tests + example)
```

### 2. 🔌 API Contracts Sub-Agent

**Purpose**: Check interfaces and API contracts exposed or consumed.

**Useful for**:
- Protocol changes impact analysis
- Breaking change detection
- Interface consistency checking
- "What's the public API of this module?"

**Example task**:

```
API Contracts sub-agent: Analyze VectorRetriever Protocol

1. List all public methods in contracts/retrieval.py:VectorRetriever
2. For each method: signature, return type, docstring
3. List all implementations (adapters)
4. Check if implementations match Protocol exactly
5. Find any violations (methods in impl but not in Protocol)

Return: Protocol definition + compliance matrix
```

**Expected output**:

```
VectorRetriever Protocol Analysis
==================================

Protocol Definition (contracts/retrieval.py):
  - def retrieve(query: str, k: int) -> List[Document]
  - def name() -> str
  - def clear_cache() -> None

Implementations (Compliant ✅):
  - adapters/vectorstores/qdrant_retriever.py → Implements all 3 methods
  - adapters/vectorstores/chroma_retriever.py → Implements all 3 methods

Implementations (Non-Compliant ❌):
  - None

Violations Detected:
  - None (all implementations match Protocol exactly)

Breaking Changes Risk (if Protocol changed):
  - 2 implementations would need updates
  - 3 tests would need updates
  - Example code would need updates
```

### 3. 🧪 Tests Sub-Agent

**Purpose**: List existing tests, coverage, and untested areas.

**Useful for**:
- Coverage gaps analysis
- Test impact of changes
- "What tests cover this code?"
- Planning test improvements

**Example task**:

```
Tests sub-agent: Analyze test coverage for ingestion/

1. List all test files in tests/unit/ingestion/
2. For each chunker implementation, list tests:
   - FixedChunker tests
   - RegexChunker tests
   - WordCountChunker tests (NEW)
3. Coverage: lines covered / total lines
4. Gaps: what's tested vs not tested
5. Patterns: common test patterns to follow

Return: Test inventory + coverage matrix + recommendations
```

**Expected output**:

```
Ingestion Module Test Coverage
================================

Test Files (4 total):
  - tests/unit/ingestion/chunkers/test_fixed.py (120 lines)
  - tests/unit/ingestion/chunkers/test_regex.py (95 lines)
  - tests/unit/ingestion/test_parser.py (150 lines)
  - tests/unit/ingestion/test_loader.py (180 lines)

Coverage by Component:
  - FixedChunker: 5 tests, 87% coverage
  - RegexChunker: 4 tests, 76% coverage
  - DocumentParser: 8 tests, 92% coverage
  - FileLoader: 6 tests, 68% coverage

Untested Areas:
  - FixedChunker.chunk() with text >50KB (edge case)
  - RegexChunker error handling for bad regex
  - FileLoader with missing files (no negative test)
  - DocumentParser with malformed documents

Recommendations:
  1. Add 3 tests for FixedChunker edge cases
  2. Add error handling test for RegexChunker
  3. Add negative tests for FileLoader
  4. Consider parametrized tests for encoding variations
```

### 4. 🧠 Main Flow Sub-Agent

**Purpose**: Synthesize results from other sub-agents and make implementation decisions.

**Role**: This is YOU. The main agent synthesizes and decides.

**Example**:

After Mapping, API Contracts, and Tests sub-agents complete, main agent receives:

```
[From Mapping] VectorRetriever is used in 9 places
[From API Contracts] 2 implementations, all compliant
[From Tests] 5 tests, 85% coverage, 1 gap identified

Decision needed: Can I safely rename VectorRetriever to VectorStore?

Options:
A) Rename directly (requires 13 changes + update tests)
B) Add alias first, deprecate old name (safer)
C) Create wrapper (not breaking, cleaner)

Recommendation: Option B (alias + deprecate) is safest
```

---

## Example: Parallel Workflow for Complex Task

### Scenario: "Add support for hybrid retrieval (BM25 + vector)"

This is complex because:
- Needs new Retriever implementation (ingestion change)
- Needs new reranker (retrieval change)
- Needs to integrate with existing VectorRetriever
- Needs tests, docs, manifest updates
- Could break existing workflows

### Step 1: Launch 3 Sub-Agents in Parallel

```
Main Agent: "I want to add hybrid retrieval support. 
Analyze 3 dimensions in parallel:"

Mapping Sub-Agent:
  "Explore VectorRetriever usage in the codebase.
   Where is it used? What would break if I add HybridRetriever?"

API Contracts Sub-Agent:
  "Analyze VectorRetriever Protocol.
   Is the interface sufficient for a hybrid variant?
   What changes to Protocol would be needed?"

Tests Sub-Agent:
  "Analyze retrieval tests.
   What test patterns should HybridRetriever follow?
   What coverage gaps exist?"
```

### Step 2: Wait for All Results

**Mapping Sub-Agent returns**:
```
VectorRetriever used in:
- tests/unit/retrieval/ (4 tests)
- tests/e2e/test_simple_qa_pipeline.py (1 test)
- examples/simple_qa/main.py (1 example)
- manifests/presets/local-hybrid-rag.yaml (1 config)
- No direct imports elsewhere

Impact: Adding HybridRetriever is low-risk (isolated in retrieval/)
```

**API Contracts Sub-Agent returns**:
```
VectorRetriever Protocol:
- def retrieve(query: str, k: int) -> List[Document]
- def name() -> str

HybridRetriever could:
A) Implement same Protocol (requires fusion logic for score combination)
B) Extend Protocol with additional params (BREAKING)
C) Wrap VectorRetriever (composition over inheritance)

Recommendation: Option A (same Protocol, internal fusion)
```

**Tests Sub-Agent returns**:
```
Retrieval test patterns:
- All retrievers tested with same test class
- Common tests: retrieve(), name(), caching
- HybridRetriever specific tests:
  - BM25 + vector fusion correctness
  - Weighted combination of scores
  - Edge cases: empty text, no matches

Test templates to follow:
- tests/unit/retrieval/test_vector.py (use as template)
- Contract test: tests/contract/test_retrieval_conformance.py
```

### Step 3: Main Agent Synthesizes

```
Decision: Add HybridRetriever

Plan:
1. Implement HybridRetriever (implement VectorRetriever Protocol)
   - Use internal BM25 + VectorStore
   - Fusion via reciprocal rank fusion (RRF)
   - No Protocol changes needed ✅

2. Add tests following existing patterns
   - Unit tests in tests/unit/retrieval/test_hybrid.py
   - Contract test in tests/contract/test_retrieval_conformance.py
   - E2E test in tests/e2e/ (existing pattern)

3. Register in registry
   - _default_factories.py: "hybrid-retriever"

4. Update manifest
   - manifests/presets/local-hybrid-rag.yaml

5. Validate
   - ./scripts/check.sh full
   - No breaking changes ✅

Effort estimate: 2 hours
Risk: LOW (isolated, compliant with Protocol)
```

### Step 4: Implement Incrementally

```bash
# Create feature branch
git checkout -b feature/hybrid-retriever

# Step 1: Implement HybridRetriever
# Claude: "Implement src/modular_rag/retrieval/hybrid_retriever.py
#  - class HybridRetriever(VectorRetriever)
#  - Use BM25Retriever + VectorRetriever
#  - Fusion: reciprocal rank fusion"

# Validate
./scripts/check.sh quick

# Step 2: Add tests
# Claude: "Add tests/unit/retrieval/test_hybrid.py
#  - Test fusion logic
#  - Test edge cases
#  - Follow test_vector.py patterns"

./scripts/check.sh full

# Step 3: Register & configure
# Claude: "Register HybridRetriever in _default_factories.py
#  - Name: 'hybrid-retriever'
#  - Params: bm25_weight, vector_weight"

# Step 4: Full validation
./scripts/check.sh full

# Commit & push
git commit -m "feat: Add HybridRetriever with RRF fusion..."
git push origin feature/hybrid-retriever
```

---

## When to Use Each Sub-Agent

### Use Mapping Sub-Agent When:

- ✅ You're renaming a widely-used component
- ✅ You're making breaking changes
- ✅ You need to understand impact across modules
- ✅ Analyzing dependencies before deletion
- ❌ Don't use: Simple, localized changes

**Example queries**:
- "Map all usages of Chunker Protocol in the codebase"
- "Where is VectorRetriever instantiated?"
- "What would break if I change the RAGEngine signature?"

### Use API Contracts Sub-Agent When:

- ✅ You're extending a Protocol
- ✅ You're checking if implementations are compliant
- ✅ You need to understand public interfaces
- ✅ Analyzing breaking change risk
- ❌ Don't use: Internal implementation details

**Example queries**:
- "Analyze Retriever Protocol and list all implementations"
- "Check if HybridRetriever matches VectorRetriever signature"
- "What methods does Generator Protocol require?"

### Use Tests Sub-Agent When:

- ✅ You're adding new code and need to know what patterns to follow
- ✅ You're analyzing coverage gaps
- ✅ You're planning test improvements
- ✅ You need to understand existing test structure
- ❌ Don't use: Writing individual tests (do that incrementally)

**Example queries**:
- "Analyze retrieval tests and show coverage + gaps"
- "What patterns do existing retriever tests follow?"
- "List all contract conformance tests and their patterns"

### Use Main Flow Sub-Agent (You) When:

- ✅ You've gathered info from 2-3 sub-agents
- ✅ You need to make design decisions
- ✅ You're synthesizing results and planning next steps
- ✅ You're deciding between options (A vs B vs C)
- ❌ Don't use: For single-step exploration

**Example decisions**:
- "Based on all 3 analyses, here's the implementation plan"
- "Breaking change detected; recommend Option B (alias + deprecate)"
- "Test gaps found; adding 4 new tests before implementing"

---

## Parallel Workflow Best Practices

### ✅ DO: Use Clear Separation

```
Main Agent (you): "Explore 3 independent dimensions in parallel"

Mapping: "Explore X..."        [runs independently]
API: "Analyze Y..."             [runs independently]
Tests: "Check Z..."             [runs independently]
```

### ❌ DON'T: Create Sub-Agents with Dependencies

```
Main Agent: "Explore X, then based on results, explore Y"
            ↑ This defeats parallelization
            Sequential, not parallel
```

### ✅ DO: Synthesize at the End

```
All sub-agents complete → Main agent synthesizes → Decision made
```

### ❌ DON'T: Decision by Sub-Agent

```
Sub-agent: "I recommend you do X"
            ↑ Wrong; main agent decides
```

---

## Limitations & Considerations

### Context Isolation

Each sub-agent has **isolated context**. It doesn't see:
- Previous sub-agent results
- Your custom instructions in CLAUDE.md
- Project-specific patterns

**Mitigation**:
- Repeat key context in sub-agent prompt
- Share results yourself in synthesis
- Re-emphasize project rules

### Results Format

Sub-agents return unstructured results. You need to:
- Parse and organize findings
- Create decision matrix
- Write implementation plan

**Tool**: Use a template (see examples above)

### Parallel Timeouts

If sub-agents run too long:
- Check your query complexity
- Break into fewer, simpler tasks
- Run sequentially if parallel is too slow

---

## Example Templates

### Template 1: Breaking Change Analysis

```
3 Sub-Agents parallel:

Mapping:
  "Map all usages of [Component] in the codebase.
   Return: List of all usages + file locations"

API Contracts:
  "Analyze [Protocol] interface.
   Return: Method signatures + compliant implementations + violations"

Tests:
  "Analyze tests for [Component].
   Return: Test count + coverage + patterns"

Synthesis (you):
  "Based on 3 analyses, can I safely:
   A) Rename [Component]?
   B) Change signature?
   C) Deprecate and replace?
   
   Recommend safest approach + effort estimate"
```

### Template 2: Feature Addition Analysis

```
3 Sub-Agents parallel:

Mapping:
  "Explore [Feature area] in the codebase.
   Return: Current structure + existing patterns"

API Contracts:
  "Analyze existing Protocols related to [Feature].
   Return: Interfaces + extension points"

Tests:
  "Analyze existing tests for [Feature area].
   Return: Test patterns + coverage + gaps"

Synthesis (you):
  "Based on 3 analyses, plan [Feature] implementation:
   - Extend Protocol or create new?
   - Follow existing patterns?
   - Test gaps to fill?
   - Effort estimate?"
```

---

## References

- [CLAUDE.md](../../CLAUDE.md) — Project rules (share with sub-agents)
- [docs/guides/onboarding-claude-code.md](onboarding-claude-code.md) — Team onboarding
- [docs/guides/validation.md](validation.md) — Validation commands
- [.claude/.instructions.md](../../.claude/.instructions.md) — Architecture rules
