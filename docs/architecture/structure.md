# Complete Structure of the Modular RAG Framework — Exhaustive Explanation

> This document describes every folder, every file, and every concept of the framework in full detail, with the current role and future role (V1→V5) of each.

---

## Overview of the root tree

```
modular-rag-framework/
├── src/                          ← Main source code
│   └── modular_rag/              ← Installable Python package
├── tests/                        ← Test suite (unit, contract, integration, e2e)
├── docs/                         ← Complete technical documentation
├── manifests/                    ← YAML pipeline configurations
├── examples/                     ← Runnable example applications
├── benchmarks/                   ← Performance benchmarks (future)
├── scripts/                      ← Utility scripts and local audits
├── .claude/                      ← Claude Code skills, hooks, and settings
├── .codex/                       ← Codex project notes
├── AGENTS.md                     ← Codex instructions and reviewer strategy
├── .gitlab/                      ← Legacy GitLab CI/CD templates (repo now hosted on GitHub)
├── pyproject.toml                ← Python project configuration
├── README.md                     ← Pitch, vision, target API
├── CLAUDE.md                     ← Instructions for Claude Code
├── CLAUDE.local.example.md       ← Template for local Claude Code preferences
├── ROADMAP.md                    ← V1→V5 milestones with checkboxes
├── CHANGELOG.md                  ← Version history
├── CONTRIBUTING.md               ← Contribution guide
└── LICENSE                       ← Apache License 2.0
```

---

## ROOT FILES

### `pyproject.toml`
Central project configuration. Replaces `setup.py` + `setup.cfg`.

**Build system**: Hatchling. The package lives in `src/modular_rag/`.

**Runtime dependencies (minimal core, always installed)**

| Package | Version | Role |
|---|---|---|
| `pydantic` | ≥2.7 | Data models, validation |
| `pydantic-settings` | ≥2.3 | Environment variable loading |
| `pyyaml` | ≥6.0 | YAML manifest loading |
| `httpx` | ≥0.27 | Asynchronous HTTP client |
| `structlog` | ≥24.1 | Structured JSON logging |
| `python-ulid` | ≥2.0 | ULID generation (time-sortable IDs) |

**Extras groups (optional dependencies)**

| Group | Command | What it adds |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | FastAPI, Uvicorn, Typer, pymupdf, docx, BS4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, cohere, tiktoken |
| `v3` | `pip install -e ".[v3]"` | neo4j, networkx, spacy, python-louvain (communities) |
| `v4` | `pip install -e ".[v4]"` | opentelemetry-sdk, opentelemetry-api, opentelemetry-exporter-otlp |
| `v5` | `pip install -e ".[v5]"` | pymupdf, pillow, pytesseract (vision) |
| `dev` | `pip install -e ".[dev]"` | pytest, pytest-asyncio, mypy, ruff, httpx, respx |
| `all` | `pip install -e ".[all]"` | Everything above |

**CLI entry point**: `mrag` → `modular_rag.cli:app` (command installed on the PATH)

**Tool configuration**
- `pytest`: automatic asyncio mode
- `mypy`: strict + pydantic plugin
- `ruff`: 100 chars per line, Python 3.11

---

### `README.md`
Commercial pitch and target API reference. Main sections:
- Why this framework (comparison table vs. LangChain, LlamaIndex)
- V1→V5 vision and 6-plane architecture
- Target API snippets (illustrative code, not yet executable)
- Pre-alpha status + installation instructions

---

### `CLAUDE.md`
Architectural instructions for Claude Code. Contains:
- Project state (what is implemented, what is missing)
- The 7 convention rules (contracts first, no cross-domain imports, manifests as source of truth…)
- Common commands (pytest, mrag, uvicorn)
- The Claude Code workflows exposed by `.claude/skills/`
- The post-edit-quality hook and the layering audit
- Info on the GitHub repo

See also [`docs/guides/claude-code.md`](../guides/claude-code.md) for the usage and
maintenance guide for this configuration.

### `AGENTS.md`
Persistent instructions for Codex. Defines Codex as the independent reviewer/challenger,
describes the diff-review rules, the editing limits, and the model-tier escalation policy.

### `.codex/`
Codex-specific project notes. The folder stays minimal: durable rules live in
`AGENTS.md`, detailed workflows in `docs/guides/`.

---

### `ROADMAP.md`
Milestone checkboxes per version. Delivery criteria per version:
- v0.1 → `examples/simple_qa/` working end-to-end
- v0.2 → `pip install -e ".[v1]"` + all V1 unit tests pass
- v1.0 → V1 complete
- v2.0 → V2 complete (agents, adaptive routing)

---

### `CHANGELOG.md`
Keep A Changelog format. The `[Unreleased]` section contains all additions since v0.0.1: full implementation of the V1→V5 skeleton, 5 manifests, 3 ADRs, architecture docs, guides, examples.

---

### `CONTRIBUTING.md`
5-step guide for adding a component (example: a new chunker): check contract → implement → register in `_default_factories.py` → manifest → tests. MR checklist included.

---

### `LICENSE`
Apache License 2.0 — Copyright 2026 Publicis Groupe — Data Specialists. Apache 2.0 was chosen over MIT for the explicit patent clause (enterprise AI/ML standard).

---

## `src/modular_rag/` — THE MAIN PACKAGE

The package follows a strict 13-layer **hexagonal architecture**. The fundamental rule: dependencies only flow downward (`core/` depends on nothing, `contracts/` depends only on `core/`, domain modules depend only on `contracts/` + `core/`).

```
src/modular_rag/
├── __init__.py              → __version__ = "0.0.1"
├── core/                    ← Foundation layer — depends on nothing
├── contracts/               ← Interfaces (Protocols) — depends on core/ only
├── adapters/                ← External bindings — implements contracts/
├── ingestion/               ← Domain: file → Document → Chunk
├── retrieval/               ← Domain: Query → list[RetrievedChunk]
├── generation/              ← Domain: context → Answer
├── security/                ← Domain: filtering, detection, redaction, policies
├── agents/                  ← Domain: V2 multi-agent runtime
├── memory/                  ← Domain: V3 knowledge graph
├── eval/                    ← Domain: metrics and benchmarks
├── observability/           ← Domain: structured telemetry
├── orchestration/           ← Runtime: engine, registry, router, compiler
├── app/                     ← Process-level wiring: bootstrap, container, settings
├── cli/                     ← Edge: Typer CLI (`mrag ask`, `mrag ingest`)
└── api/                     ← Edge: FastAPI REST API
```

---

### `core/` — The foundation layer

**Rule**: `core/` imports nothing from this project. It is the base of everything.

#### `core/enums.py`

7 `StrEnum` enums (values = Python strings, not integers):

| Enum | Values | Usage |
|---|---|---|
| `Modality` | text, image, table, audio, video, code | Content type of a Document/Chunk |
| `RetrievalMethod` | vector, bm25, hybrid, graph, multimodal | How a RetrievedChunk was found |
| `ChunkingStrategy` | fixed, sentence, paragraph, section, adaptive, semantic | Chunking strategy (in the manifest) |
| `RoutingStrategy` | llm_only, simple_rag, agentic_rag, graph_rag, multimodal_rag | Strategy chosen by the Router |
| `PolicyAction` | allow, deny, redact, warn, require_review | Action of a PolicyRule |
| `AgentRole` | coordinator, planner, retriever, extractor, synthesizer, validator, critic | Role of a V2 agent |
| `GraphRelation` | depends_on, causes, is_part_of, works_for, contradicts, supports, derives_from | Relation type in the V3 graph |


#### `core/ids.py`
- `new_id()` → ULID (Universally Unique Lexicographically Sortable Identifier, based on UUID4). Sorted by creation time.
- `short_id()` → first 8 characters of the ULID. Used for human-readable labels.

#### `core/errors.py`
Complete exception hierarchy:

```
ModularRAGError                ← base
├── ConfigurationError         ← invalid manifest or settings
│   └── ManifestError          ← YAML not loadable
├── RegistryError              ← component not found in the registry
├── IngestionError             ← parsing or chunking failed
├── IndexingError              ← vector/lexical store write failed
├── RetrievalError             ← retrieval failed
├── GenerationError            ← LLM call failed
├── SecurityError              ← query or answer blocked
│   └── PolicyViolationError   ← policy rule violated
├── EvaluationError            ← scoring or benchmark failed
├── GraphError                 ← V3 graph failed
├── AgentError                 ← V2 agent task failed
└── StorageError               ← storage backend failed
```

#### `core/models/` — The domain entities

All Pydantic v2 `BaseModel`. No ORM, no DB mapping.

**`document.py` → `Document`** (`frozen=True`)
- Atomic unit of ingestion. Once created from a file, its content never changes.
- Fields: `id` (auto ULID), `source` (path or URL), `content` (raw extracted text), `modality`, `mime_type`, `metadata`, `created_at`
- Invariant: `frozen=True` — any mutation produces a new instance.

**`chunk.py` → `Chunk`** (`frozen=False`)
- Sub-segment of a Document. Mutable to allow writing the embedding after creation.
- Fields: `id`, `doc_id` (reference to the parent Document), `content`, `modality`, `embedding` (list[float] | None), `start_char`, `end_char`, `page`, `metadata`
- Computed property: `token_estimate` = `len(content.split())` — an approximation, not stored.

**`query.py` → `Query`** (`frozen=True`)
- Immutable user query. The text cannot change mid-pipeline (it would break correlation with the Trace).
- Fields: `id`, `text`, `modality`, `routing_hint` (optional RoutingStrategy to force a strategy), `metadata`, `created_at`

**`retrieved.py` → `RetrievedChunk`** (`frozen=True`)
- Chunk wrapped with its retrieval metadata.
- Fields: `chunk` (Chunk), `score` (float 0–1), `rank` (int 1-based), `retrieval_method`
- `__lt__` defined to allow `sorted(list_of_retrieved_chunks)` by rank.

**`answer.py` → `Citation` + `Answer`**
- `Citation`: pointer from the answer to a source chunk. Fields: `chunk_id`, `source`, `passage` (verbatim excerpt, truncated to 300 chars), `score`, `page`, `metadata`
- `Answer`: generated text + list of citations + traceability metadata. Fields: `id`, `query_id`, `text`, `citations`, `confidence`, `trace_id`, `model`, `metadata`, `created_at`

**`trace.py` → `TraceStep` + `Trace`**
- `TraceStep`: metrics for one step (`name`, `input_tokens`, `output_tokens`, `latency_ms`, `metadata`)
- `Trace`: accumulates steps via `add_step()`. The call atomically updates `total_latency_ms`, `total_input_tokens`, `total_output_tokens`.
- Linked to the Answer via `Answer.trace_id = trace.id`

**`policy.py` → `PolicyRule` + `Policy`** (V4)
- `PolicyRule`: a rule with `condition` (DSL expression or regex), `action` (PolicyAction), `priority` (int)
- `Policy`: group of rules scoped to a `tenant` and pipelines (`scope`). `sorted_rules()` sorts by descending priority.

**`metrics.py` → `Metrics`**
- Flat bag of evaluation scores (all optional). `summary()` returns only the non-None fields.
- Fields: `recall_at_k`, `precision_at_k`, `ndcg`, `mrr`, `groundedness`, `faithfulness`, `answer_relevance`, `context_precision`, `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`

---

### `contracts/` — The framework interfaces

**Rule**: All `Protocol`s are `@runtime_checkable`. No concrete class inherits from these Protocols — conformance is structural (duck typing verified at runtime via `isinstance(obj, Protocol)`).

| File | Exported Protocol(s) | Key methods | Version |
|---|---|---|---|
| `chunking.py` | `Chunker` | `chunk(doc) → list[Chunk]`, `name() → str` | V1 |
| `embeddings.py` | `Embedder` | `embed(texts) → list[list[float]]`, `aembed()`, `dimensions`, `name()` | V1 |
| `retrieval.py` | `Retriever` | `retrieve(query, k) → list[RetrievedChunk]`, `aretrieve()`, `name()` | V1 |
| `generation.py` | `Generator` | `generate(query, context, trace) → Answer`, `agenerate()`, `name()` | V1 |
| `reranking.py` | `Reranker` | `rerank(query, chunks, k) → list[RetrievedChunk]`, `name()` | V1 |
| `security.py` | `SecurityGuard`, `Redactor`, `GuardResult` | `check_query()`, `check_answer()`, `redact()` | V1 |
| `evaluation.py` | `Evaluator` | `evaluate(query, answer, expected, context) → Metrics`, `name()` | V1 |
| `indexing.py` | `Indexer` | `index(chunks) → int`, `delete(ids)`, `clear()`, `name()` | V1 |
| `storage.py` | `Storage` | `put(key, value)`, `get(key)`, `delete(key)`, `exists(key)` | V1 |
| `telemetry.py` | `Telemetry` | `record_trace(trace)`, `record_metrics(metrics)`, `name()` | V1 |
| `planning.py` | `Planner`, `ExecutionPlan`, `ExecutionStep` | `plan(query) → ExecutionPlan` | V2 |
| `agents.py` | `Agent`, `AgentTask`, `AgentResult` | `run(task) → AgentResult`, `arun()`, `role()`, `name()` | V2 |
| `manifests.py` | `ManifestLoader`, `PipelineManifest`, `ComponentConfig` | `load(path) → PipelineManifest` | V1 |

**`PipelineManifest`** is the complete schema of a YAML manifest. It contains a `ComponentConfig` for each role (chunker, embedder, indexer, retriever, reranker, generator, guard, evaluator, telemetry) plus optional sections for V2 (planner, agents), V3 (graph_store), V4 (policies), V5 (modalities).

---

### `adapters/` — External bindings

**Role**: Isolate heavy external dependencies. A `BM25Retriever` test must not require `sentence-transformers` to be installed.

#### `adapters/embeddings/`

**`openai_embedder.py` → `OpenAIEmbedder`**
- Implements `Embedder`. Lazy import of `openai`.
- Init: `model` (e.g. `text-embedding-3-small`), `api_key`, `batch_size=64`
- `embed()`: batches the texts, calls the synchronous API
- `aembed()`: uses `AsyncOpenAI`
- `dimensions`: property returning the vector size from a `_DIMENSIONS` dict

**`hf_embedder.py` → `HuggingFaceEmbedder`**
- Implements `Embedder`. Lazy import of `sentence-transformers`.
- Init: `model="BAAI/bge-small-en-v1.5"`, `batch_size=32`, `device="cpu"`
- `_get_model()`: lazy loading of the `SentenceTransformer`
- `aembed()`: uses `asyncio.run_in_executor` (thread pool, since sentence-transformers is synchronous)

#### `adapters/vectorstores/`

**`qdrant_store.py` → `QdrantStore`**
- Implements `Indexer` + low-level retriever. Lazy import of `qdrant-client`.
- `_ensure_collection()`: creates the Qdrant collection if it does not exist (cosine distance)
- `index(chunks)`: upserts `PointStruct`s with vector + full payload
- `retrieve_by_vector(vector, k)`: `client.search()` → rebuilds `Chunk`s from the payload
- `retrieve()`: raises `NotImplementedError` — the full retriever requires an `Embedder` to be wired in

#### `adapters/llms/`, `adapters/auth/`, `adapters/graphstores/`, `adapters/search/`
**Current state**: `.gitkeep` only. Placeholders for:
- `adapters/llms/`: OpenAI/Anthropic generators as adapters (currently in `generation/`)
- `adapters/auth/`: API key / OAuth validation
- `adapters/graphstores/`: Neo4j (currently KnowledgeGraph is in-memory in `memory/`)
- `adapters/search/`: web search tools (Tavily, Brave…)

---

### `ingestion/` — Document processing pipeline

**Flow**: `File → Parser → TextNormalizer → MetadataEnricher → Chunker → list[Chunk]`

#### `ingestion/parsers/`

**`text_parser.py` → `TextParser`**
- Supports: `.txt`, `.md`, `.rst`
- `supports(path) → bool`, `parse(path) → Document` — UTF-8 read with error replacement

**`pdf_parser.py` → `PDFParser`**
- Supports: `.pdf`
- Lazy import of `fitz` (PyMuPDF, in the `v1` group)
- `parse(path) → Document` — joins pages with `\n\n`, adds `page_count` to metadata

#### `ingestion/normalizers/`

**`text_normalizer.py` → `TextNormalizer`**
- `normalize(doc) → Document` (new instance — Document is frozen)
- Operations: NFKC unicode normalization, collapse 3+ newlines → 2, collapse 2+ spaces → 1, strip

#### `ingestion/enrichers/`

**`metadata_enricher.py` → `MetadataEnricher`**
- `enrich(doc) → Document` (new instance)
- Adds to metadata: `filename`, `extension`, `size_bytes`, `enriched_at`

#### `ingestion/chunkers/`

**`fixed.py` → `FixedSizeChunker`**
- Init: `chunk_size=512` (tokens), `chunk_overlap=64`
- Sliding window over words. Tracks `start_char` / `end_char` in the original document.
- `name()` → `"fixed-size"`

**`adaptive.py` → `AdaptiveChunker`**
- Init: `chunk_size=512`, `chunk_overlap=64`
- Splits first on Markdown headings (`#` through `######`) and double newlines (regex)
- Sections that are too large → re-split with fixed-size logic
- `name()` → `"adaptive"`

#### `ingestion/pipelines/default.py`

**`ingest_path(path, chunker) → list[Chunk]`**
- Detects the appropriate parser (TextParser or PDFParser)
- Applies: parser → normalizer → enricher → chunker

**`ingest_directory(directory, chunker) → list[Chunk]`**
- Recursively walks the directory, calls `ingest_path` on every supported file

---

### `retrieval/` — Search engine

#### `retrieval/retrievers/`

**`bm25.py` → `BM25Retriever`**
- Implements `Retriever`. Lazy import of `rank-bm25`. In-memory index.
- `index(chunks)`: rebuilds the BM25 index over the new chunks
- `retrieve(query, k)`: tokenizes the query, calls `BM25Okapi.get_scores()`, filters scores > 0
- `name()` → `"bm25"`

**`vector.py` → `VectorRetriever`**
- Implements `Retriever`. Generic wrapper around an injected vector store + `Embedder`.
- `retrieve()`: embeds the query via `_embedder`, then calls `_store.retrieve_by_vector(query_vec, k)`.
- `_embedder` and `_store` are injected by `orchestration/registry.py`; the retriever never instantiates an adapter directly.
- `name()` → `"vector"`

**`hybrid.py` → `HybridRetriever`**
- Combines `VectorRetriever` + `BM25Retriever` via RRF
- Init: `vector_weight=0.7`, `bm25_weight=0.3`, `rrf_k=60`, `k=20`
- `name()` → `"hybrid"`

#### `retrieval/fusion/rrf.py`

**`reciprocal_rank_fusion(lists, k, rrf_k=60) → list[RetrievedChunk]`**
- Pure function. Formula: `score(d) = Σ 1 / (rrf_k + rank_i(d))`
- Deduplicates by `chunk.id`, limits to `k` results, renumbers ranks from 1 to N

#### `retrieval/rerankers/`

**`cross_encoder.py` → `CrossEncoderReranker`**
- Lazy import of `sentence-transformers`. Default model: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- `rerank(query, chunks, k)`: pairs (query.text, chunk.content) → `model.predict()` → sorts by score

#### `retrieval/planners/`

**`simple.py` → `SimplePlanner`**: Fixed plan [retrieve → rerank → generate] for V1 (SIMPLE_RAG)

**`graph.py` → `GraphPlanner`**: Plan [entity_extract → graph_retrieve → vector_retrieve → generate] for V3 (GRAPH_RAG)

---

### `generation/` — Answer synthesis

#### `generation/synthesizers/`

**`openai_gen.py` → `OpenAIGenerator`**
- Implements `Generator`. Lazy import of `openai`.
- Init: `model="gpt-4o-mini"`, `temperature=0.1`, `max_tokens=2048`, `api_key=""`
- `generate(query, context, trace)`: builds a numbered prompt [1], [2]…, calls the API, builds the citations, emits a `TraceStep` with the token counts
- `agenerate()`: async version

**`anthropic_gen.py` → `AnthropicGenerator`**
- Implements `Generator`. Lazy import of `anthropic`.
- Init: `model="claude-opus-4-7"`, `max_tokens=2048`, `api_key=""`
- Same logic as OpenAIGenerator but via the Anthropic Messages API

#### `generation/citations/builder.py`

**`build_citations(chunks) → list[Citation]`**: Pure function. Creates one `Citation` per chunk, truncates the `passage` to 300 chars.

#### `generation/validators/groundedness.py`

**`GroundednessValidator`**: `validate(answer, context) → float [0,1]` — ratio of answer tokens present in the context (word-set intersection, case-insensitive).

---

### `security/` — Defense in depth

#### `security/filters/`

**`basic_guard.py` → `BasicSecurityGuard`** (V1)
- Implements `SecurityGuard`. Init: `max_query_length=4000`
- 4 injection regex patterns: `ignore * instructions`, `disregard * prompt`, `you are now | pretend`, `jailbreak | DAN mode`
- `frozenset` of blocked terms: `rm -rf`, `os.system`, `exec(`, `__import__`
- `risk_score`: 0.9 (injection) | 0.8 (blocked term) | 0.5 (too long) | 0.0 (OK)
- `check_answer()`: pass-through in V1 (always allowed)

#### `security/detectors/`

**`adversarial.py` → `AdversarialDetector`** (V2)
- Patterns: `send to email/slack/webhook`, `output all documents`, `base64/curl` exfiltration
- `risk_score` = 0.95 for exfiltration

#### `security/redaction/`

**`patterns.py` → `PatternRedactor`**
- Implements `Redactor`. 4 PII patterns → `[REDACTED]`:
  - `email`: `\b[A-Za-z0-9._%+-]+@...\b`
  - `phone_fr`: `\b0[1-9](?:[\s.-]?\d{2}){4}\b`
  - `iban`: `\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}...\b`
  - `api_key`: `\b(?:sk|pk|api|token)[-_][A-Za-z0-9]{20,}\b`

#### `security/policies/`

**`policy_engine.py` → `PolicyEngine`** (V4)
- Init: `policies: list[Policy]`
- `enforce_query(query)`: filters enabled policies, evaluates rules in descending priority order
- DENY → `raise PolicyViolationError`; WARN → log + allow
- `_evaluate()`: keyword matching (extensible toward CEL/OPA Rego)

---

### `agents/` — Multi-agent runtime (V2)

**`agents/coordinator/coordinator.py` → `CoordinatorAgent`**
- Init: `agents: dict[AgentRole, Agent]`
- `execute_plan(plan, query)`: iterates over the `ExecutionPlan` steps, dispatches each step to the agent by role/name

**`agents/retriever/retriever_agent.py` → `RetrieverAgent`**: Adapts a `Retriever` as an `Agent`. Init: `retriever: Retriever`, `k: int = 10`

**`agents/extractor/extractor.py` → `ExtractorAgent`**: Named entity extraction via regex. Deduplicates, limits to 30 unique entities.

**`agents/synthesizer/synthesizer.py` → `SynthesizerAgent`**: Concatenates the top-5 context chunks. Limits the draft to 2000 chars.

**`agents/validator/validator.py` → `ValidatorAgent`**: Computes a local groundedness score via token overlap (does not import `generation/validators/groundedness.py` — cross-domain imports are forbidden here). Adds a warning if score < 0.05.

---

### `memory/` — Persistent memory (V3)

**`memory/kv/in_memory.py` → `InMemoryStorage`**: Implements `Storage`. Plain Python dict. Not thread-safe, for dev/tests only.

**`memory/graph/knowledge_graph.py` → `GraphNode` + `GraphEdge` + `KnowledgeGraph`**
- `GraphNode`: id, label, type, properties, source_chunk_ids
- `GraphEdge`: source_id, target_id, relation (GraphRelation), weight, properties
- `KnowledgeGraph`:
  - `add_node()`, `add_edge()`, `get_node()`
  - `neighbours(node_id, hops)`: BFS for N hops
  - `subgraph_for_query(entity_labels, hops)`: seed from labels → BFS expansion
  - `stats()`: {nodes, edges}
- In-memory backend, swappable with the Neo4j adapter (future)

**`memory/versioning/graph_versioning.py` → `GraphVersionManager`** (EvoRAG)
- `reinforce(source_id, target_id, delta=0.1)`: increases an edge's weight (positive feedback)
- `weaken(source_id, target_id, delta=0.1)`: decreases the weight (negative feedback)
- `prune(min_weight=0.1)`: removes edges below the threshold
- Bounds: weight ∈ [0.0, 1.0]

---

### `eval/` — Evaluation

**`eval/scorers/exact_match.py` → `ExactMatchEvaluator`**
- Implements `Evaluator`. Precision/Recall/F1 over token sets. Case-insensitive.
- If `expected=None`, returns `Metrics` with `None` scores. `name()` → `"exact-match"`

**`eval/scorers/retrieval_metrics.py`**: Pure functions `recall_at_k()`, `precision_at_k()`, `mrr()`. `compute_retrieval_metrics()` aggregates them into a single `Metrics`.

**`eval/runners/benchmark.py` → `BenchmarkCase` + `BenchmarkReport` + `BenchmarkRunner`**
- `BenchmarkCase`: question, expected_answer, relevant_chunk_ids
- `BenchmarkRunner.run(cases)`: walks through the cases, calls `engine.answer()`, computes the metrics
- `BenchmarkReport`: metrics_per_case + `avg_answer_relevance`, `avg_recall`

---

### `observability/`

**`StructlogTelemetry`**: Implements `Telemetry`. Structured JSON logs via structlog.

**`NullTelemetry`**: Implements `Telemetry`. No-op for tests (zero overhead).

---

### `orchestration/` — Runtime engine

#### `orchestration/engine.py` → `RAGEngine`

The main conductor. Uses the Container to access all components.

**`ingest(documents)`**:
1. Embeds the chunks with `container.embedder.embed()`
2. Indexes with `container.indexer.index()`
3. If the retriever is BM25: `retriever.index(chunks)` as well

**`answer(question, **kwargs)`**:
1. Creates `Query` + `Trace`
2. `guard.check_query(query)` → `SecurityError` if refused
3. `retriever.retrieve(query, k=20)`
4. `reranker.rerank(query, chunks, k=5)` (if configured)
5. `generator.generate(query, context, trace)`
6. `guard.check_answer(answer)` (if configured)
7. `telemetry.record_trace(trace)` (if configured)

**`retrieve(question, k)`**: Retrieval only, no generation.

#### `orchestration/_default_factories.py`
Lazy factory callables for all built-in components. `register_defaults(reg)` is called by `ComponentRegistry.default()`.

#### `orchestration/registry.py` → `ComponentRegistry`
Maps `(role, type_name)` → `factory callable`.
- `register(role, type_name, factory)`: adds a factory
- `wire(manifest) → Container`: for each role in the manifest, calls `factory(config)`, stores in the Container
- `default()`: classmethod that pre-loads `_default_factories`

#### `orchestration/router.py` → `QueryRouter`
Classifies each query into a `RoutingStrategy`:
- `routing_hint` on the Query → direct override
- Graph keywords → `GRAPH_RAG`
- Agentic keywords OR >40 words → `AGENTIC_RAG`
- <5 words → `LLM_ONLY`
- Otherwise → `SIMPLE_RAG`

#### `orchestration/flow_compiler.py` → `FlowCompiler`
`compile(query, strategy) → ExecutionPlan` with step templates:
- **LLM_ONLY**: [generate]
- **SIMPLE_RAG**: [retrieve → rerank → generate]
- **AGENTIC_RAG**: [plan → retrieve_agent → synthesizer_agent → validator_agent → output]
- **GRAPH_RAG**: [graph_retrieve → retrieve → generate]

#### `orchestration/state_machine.py` → `PipelineStateMachine`
States: `IDLE → GUARDING_QUERY → RETRIEVING → RERANKING → GENERATING → GUARDING_ANSWER → EVALUATING → DONE` (+ `ERROR`)
Hard-coded transition matrix. `transition(to)` validates and logs every state change.

---

### `app/` — Process-level wiring

#### `app/settings.py` → `Settings`
Pydantic-settings with the `MRAG_` prefix. Reads from `.env` + environment variables.

```
MRAG_OPENAI_API_KEY, MRAG_ANTHROPIC_API_KEY
MRAG_LLM_MODEL, MRAG_TEMPERATURE, MRAG_MAX_TOKENS
MRAG_EMBEDDING_MODEL, MRAG_EMBEDDING_BATCH_SIZE
MRAG_QDRANT_URL, MRAG_QDRANT_API_KEY, MRAG_QDRANT_COLLECTION
MRAG_K, MRAG_RERANKER_K, MRAG_VECTOR_WEIGHT, MRAG_BM25_WEIGHT
MRAG_CHUNK_SIZE, MRAG_CHUNK_OVERLAP
MRAG_SECURITY_ENABLED
MRAG_TELEMETRY_ENABLED, MRAG_OTEL_ENDPOINT, MRAG_LOG_LEVEL
MRAG_NEO4J_URL, MRAG_NEO4J_USER, MRAG_NEO4J_PASSWORD
```

`get_settings()`: singleton (a single `.env` read per process).

#### `app/container.py` → `Container`
DI Container. Internal `_store: dict[str, Any]`.
- `register(name, component)`: stores an instance
- Typed properties: `container.chunker`, `container.embedder`, `container.retriever`… Return `None` for optional components not configured.

#### `app/bootstrap.py`
- `load_manifest(path) → PipelineManifest`: reads the YAML, validates via Pydantic
- `load_pipeline(path) → RAGEngine`: `load_manifest` → `ComponentRegistry.default()` → `registry.wire(manifest)` → `RAGEngine(container)`

#### `app/lifecycle.py`
- `startup(container)` + `shutdown(container)`: startup/shutdown hooks (currently just logging — placeholder for managing DB connections, cleanup, etc.)

---

### `cli/` — Command-line interface

**`cli/__init__.py`** → `app` (Typer instance, `mrag` entry point)

Commands:
- `mrag ingest <path> --manifest <yaml>`: loads the pipeline, ingests the documents, prints the number indexed
- `mrag ask "<question>" --manifest <yaml>`: loads the pipeline, asks the question, prints the answer + citations formatted with scores
- `mrag version`: prints `__version__`

---

### `api/` — REST API

**`api/__init__.py`** → `create_app(manifest_path) → FastAPI`

Factory pattern. Endpoints:
- `GET /health` → `{"status": "ok", "pipeline": "<manifest_id>"}`
- `POST /answer` (body: `QuestionRequest{question, k}`) → `AnswerResponse{text, citations, trace_id}`
- `GET /retrieve?q=<question>&k=<n>` → `[{chunk_id, score, content_preview}]`

Error codes: 403 (SecurityError), 422 (Pydantic validation), 500 (internal errors).

---

## `tests/` — Test suite

```
tests/
├── __init__.py
├── unit/                    ← Fast, no external services required
│   ├── core/test_models.py
│   ├── ingestion/
│   │   ├── chunkers/test_fixed.py
│   │   ├── chunkers/test_adaptive.py
│   │   └── test_normalizer.py
│   ├── retrieval/test_rrf.py
│   ├── security/
│   │   ├── test_basic_guard.py
│   │   └── test_redaction.py
│   ├── eval/test_exact_match.py
│   └── memory/test_knowledge_graph.py
├── contract/                ← Verify that an implementation satisfies its Protocol
│   ├── test_chunker_conformance.py      (FixedSizeChunker + AdaptiveChunker)
│   ├── test_retrieval_conformance.py    (BM25Retriever — VectorRetriever excluded, needs Qdrant)
│   ├── test_security_conformance.py     (BasicSecurityGuard + PatternRedactor)
│   └── test_eval_conformance.py         (ExactMatchEvaluator)
├── integration/             ← Require Qdrant on localhost:6333 (currently empty)
├── e2e/                     ← Full pipeline with real LLM (currently empty)
├── benchmark/               ← Performance benchmarks (currently empty)
└── fixtures/                ← Shared fixtures (currently empty)
```

**Unit tests — per-file detail**

| File | What is tested | Cases |
|---|---|---|
| `test_models.py` | Document frozen, Chunk token_estimate, Query frozen, RetrievedChunk __lt__, Trace.add_step accumulation, Metrics.summary, Policy.sorted_rules | 30+ |
| `test_fixed.py` | Short text → 1 chunk, long text → N chunks, overlap, doc_id, start_char/end_char, empty doc | 8 |
| `test_adaptive.py` | Splits on Markdown headings, doc_id, flat text, empty doc | 6 |
| `test_normalizer.py` | Collapse newlines, collapse spaces, strip, preserves semantics, returns Document | 5 |
| `test_rrf.py` | Single list preserves order, deduplication by chunk.id, shared-doc boost, k limit, empty lists, renumbering | 7 |
| `test_basic_guard.py` | Benign query, injection blocked, jailbreak blocked, max length | 7 |
| `test_redaction.py` | Email, multiple emails, FR phone, benign text unchanged, API key | 5 |
| `test_exact_match.py` | Perfect match, no overlap, partial overlap, case-insensitive, expected=None | 6 |
| `test_knowledge_graph.py` | add/get node, missing node → None, add_edge + neighbours, hops, stats(), subgraph_for_query | 8 |

**Conformance tests — logic**
- `isinstance(obj, Protocol)` → verifies structural conformance at runtime
- Tests parameterized over all implementations of a given Protocol
- VectorRetriever and HybridRetriever **excluded** from contract tests (require Qdrant)

---

## `docs/` — Documentation

```
docs/
├── adr/
│   ├── 0001-modular-architecture.md   ← 6 planes, dependency rule
│   ├── 0002-contracts-and-plugins.md  ← Protocol vs ABC, factory registry
│   └── 0003-security-and-governance.md ← Safety vs Security, layered plan
├── api/
│   └── rest.md                  ← REST reference (endpoints, schemas, error codes)
├── architecture/
│   ├── overview.md              ← V1→V5 technical spec, 6 planes, contracts, wiring, RRF, errors
│   ├── data-model.md            ← All Pydantic models, fields, invariants, lifecycle
│   ├── module-model.md          ← Module tree, dependency rules, adapter pattern
│   ├── runtime-flow.md          ← Mermaid sequences V1 (query + ingestion + data lifecycle), V2, V3
│   ├── security.md              ← Attack surfaces, guard chain, regex patterns, PII types, risk_score
│   ├── structure.md             ← This file — exhaustive explanation of the entire structure
│   └── roadmap-mermaid.md       ← 5 Mermaid diagrams (timeline, dependencies, wiring V1, V2, V3)
├── guides/
│   ├── getting-started.md       ← 5-step walkthrough: Qdrant → API key → ingest → ask
│   ├── installation.md          ← Prerequisites, extras groups, Qdrant Docker, env variables
│   ├── deployment.md            ← Dockerfile, docker-compose, multi-env manifests
│   ├── observability.md         ← StructlogTelemetry JSON, NullTelemetry, custom adapter
│   └── plugin-development.md    ← 4-step recipe for adding a component
└── reviews/
    └── 2026-05-20-initial-review.md ← Initial review (strengths, weaknesses, P0/P1 decisions)
```

---

## `manifests/` — YAML configurations

```
manifests/
├── presets/
│   ├── local-hybrid-rag.yaml         ← V1 local dev (HuggingFace + Qdrant localhost + GPT-4o-mini)
│   ├── secure-enterprise-rag.yaml    ← V1 prod (guard + policies + GPT-4o, temp=0.0)
│   ├── agentic-rag.yaml              ← V2 (5 agents + coordinator + adaptive routing)
│   ├── graph-memory-rag.yaml         ← V3 (GraphPlanner + NetworkX + EvoRAG feedback)
│   └── multimodal-rag.yaml           ← V5 (CLIP + Whisper + claude-opus-4-7 + modality agents)
├── dev/                              ← Dev environment overrides (V4, currently empty)
├── staging/                          ← Staging overrides (V4, currently empty)
└── production/                       ← Production overrides (V4, currently empty)
```

| Manifest | Version | LLM | Embedder | Security | Notable |
|---|---|---|---|---|---|
| `local-hybrid-rag` | V1 | gpt-4o-mini | bge-small-en-v1.5 | none | Development, Qdrant localhost |
| `secure-enterprise-rag` | V1 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard + policies | max_query_length=2000, temp=0.0 |
| `agentic-rag` | V2 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard | k=30, rerank_k=10, 5 agents |
| `graph-memory-rag` | V3 | gpt-4o | bge-base-en-v1.5 | BasicSecurityGuard | GraphPlanner, EvoRAG feedback |
| `multimodal-rag` | V5 | claude-opus-4-7 | CLIP + bge-base | BasicSecurityGuard | multi-vector, modality agents |

---

## `examples/` — Example applications

```
examples/
├── simple_qa/                    ← Only complete example (V1)
│   ├── main.py                   ← argparse CLI: ingest + ask
│   ├── README.md                 ← Prerequisites, 4 steps, demonstrated features
│   └── docs/
│       ├── rag-overview.md       ← Sample document about RAG (Lewis 2020, variants)
│       └── retrieval-methods.md  ← Sample document about dense/BM25/hybrid/reranking
├── agentic_rag/                  ← V2 placeholder
├── graph_memory/                 ← V3 placeholder
├── hybrid_search/                ← V1 variant placeholder
└── secure_rag/                   ← Secured V1 placeholder
```

**`examples/simple_qa/main.py`** — The reference script:

```python
# Ingestion
pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
chunks = ingest_directory("./docs", AdaptiveChunker())
pipeline.ingest(chunks)

# Question
answer = pipeline.answer("What is RAG?")
print(answer.text)
for c in answer.citations:
    print(f"  [{c.source}] score={c.score:.3f} — {c.passage[:80]}…")
```

---

## Implementation roadmap per version

| Version | Theme | Status | What remains |
|---|---|---|---|
| **V1** | Core RAG | ~95% | Stabilize integration/e2e tests, `adapters/llms/` to fill in |
| **V2** | Agentic | ~100% code | E2E tests with a real LLM, `examples/agentic_rag/` |
| **V3** | Graph Memory | ~80% | `adapters/graphstores/neo4j_store.py`, spaCy NER, Louvain communities, `examples/graph_memory/` |
| **V4** | Governance | ~60% | CEL/OPA Rego evaluation, audit trail, human-in-the-loop, env-specific manifests |
| **V5** | Multimodal | ~5% | Entire modules to create (`multimodal/`, `vision/`, `tables/`, `audio/`), CLIP/Whisper adapters |

---

## Architectural principles recap

| Rule | Why |
|---|---|
| **Contracts first** | Before any concrete implementation, the Protocol exists and is tested |
| **No cross-domain imports** | A retriever cannot import from `generation/` — test isolation without an LLM |
| **Manifests as source of truth** | A component is only "enabled" if it is in the YAML — no hidden Python wiring |
| **Tests mirror src/** | `tests/unit/ingestion/chunkers/test_fixed.py` for `src/modular_rag/ingestion/chunkers/fixed.py` |
| **ADR before structural changes** | Any new layer or contract requires an ADR under `docs/adr/` |
| **Observability is mandatory** | Every retrieval/generation/agent method emits a `Trace` |
| **Safety ≠ Security** | Safety (injection, PII) in `security/filters/` and `security/redaction/`; Security (RBAC, policies) in `security/policies/` |
