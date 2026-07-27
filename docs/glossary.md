# Glossary

Terms used throughout this documentation, defined once here instead of re-explained in every
file that uses them. Each entry links to the document where the concept is covered in full
depth — this page is a map, not a replacement for those documents.

---

### Adapter
A concrete binding to an external library or service (OpenAI, Qdrant, HuggingFace) that
implements a `contracts/` Protocol. Adapters live under `adapters/` specifically so that
domain modules don't need the heavy external dependency installed to be unit-tested. See
[module-model.md](architecture/module-model.md).

### Agent
A specialized reasoning unit in the V2+ multi-agent runtime (coordinator, planner,
retriever, extractor, synthesizer, validator). Not implemented in V1, where a single
`RAGEngine` runs the pipeline sequentially instead. See [ROADMAP.md](../ROADMAP.md), V2.

### BM25 (Best Match 25)
A sparse, keyword-based lexical retrieval algorithm — ranks documents by term frequency and
inverse document frequency. Strong on exact terms and acronyms, blind to paraphrasing and
synonyms. Complements dense vector retrieval in the hybrid retriever. See
[structure.md](architecture/structure.md), `retrieval/retrievers/bm25.py`.

### Chunk
A sub-segment of a `Document`, produced by a `Chunker`. Unlike `Document`, chunks are
mutable so an `Embedder` can write the embedding vector into them after creation. See
[data-model.md](architecture/data-model.md), section 2.

### Chunking
Splitting a document into smaller pieces before indexing, because embedding models and LLM
context windows both have practical size limits, and retrieval precision improves when a
chunk covers one coherent idea rather than an entire document. The framework ships
fixed-size and adaptive (section-aware) chunkers. See
[plugin-development.md](guides/plugin-development.md).

### Citation
A pointer from a generated `Answer` back to the specific `Chunk` that supports a claim in
it — includes the source, a verbatim excerpt, and a relevance score. See
[data-model.md](architecture/data-model.md), section 5.

### ComponentRegistry
The object that maps a `(role, type_name)` pair (e.g., `("chunker", "adaptive")`) to a
factory function that builds the concrete instance. Populated by
`orchestration/_default_factories.py`, consumed when a manifest is wired into a `Container`.
See [overview.md](architecture/overview.md), section 9.

### Contract
A `typing.Protocol` in `src/modular_rag/contracts/` that defines the interface a capability
must satisfy (e.g., `Chunker`, `Retriever`, `Generator`). Chosen over abstract base classes
so that third-party implementations never need to import or subclass anything from this
framework. See [ADR-0002](adr/0002-contracts-and-plugins.md).

### Cross-encoder / Reranker
A model that scores a `(query, chunk)` pair directly (rather than comparing independent
embeddings), producing a more accurate but slower relevance score than a bi-encoder. Used to
re-score the top-k candidates after hybrid retrieval, before generation. See
[retrieval-methods.md](../examples/simple_qa/docs/retrieval-methods.md).

### Domain module
One of `ingestion/`, `retrieval/`, `generation/`, `security/`, `eval/`, `agents/`,
`memory/`, `observability/` — implements one capability, depends only on `contracts/` +
`core/models/`, and must never import from another domain module. See
[module-model.md](architecture/module-model.md).

### EvoRAG
The feedback mechanism (V3) that strengthens or weakens edges in the knowledge graph based
on whether answers derived from them turned out to be correct — implemented by
`GraphVersionManager.reinforce()`/`weaken()`/`prune()`. See
[structure.md](architecture/structure.md), `memory/versioning/`.

### Groundedness
A measure of how well an answer's claims are supported by the retrieved context, typically
computed as token overlap between the answer and the source chunks. Used both as an
evaluation metric and, in V2, as a signal for the `ValidatorAgent` to trigger a
self-correction loop. See [data-model.md](architecture/data-model.md), section 8 (`Metrics`).

### GraphRAG
Retrieval-augmented generation that queries a knowledge graph (entities + relationships)
instead of, or in addition to, plain text chunks — enables multi-hop reasoning ("who is
affected, in cascade, by X?") that vector/BM25 search alone cannot answer. V3 scope. See
[onboarding.md](onboarding.md), section 3.

### Guard / SecurityGuard
A component that inspects a query before retrieval (`check_query()`) or an answer after
generation (`check_answer()`) for injection attempts, blocked terms, excessive length, or
policy violations. See [security.md](architecture/security.md).

### Hexagonal architecture
The layering discipline this framework enforces: dependencies flow in one direction only
(`core/` → `contracts/` → domain modules → `orchestration/` → `app/` → `cli/`/`api/`), so
any component can be swapped by implementing its Protocol, without the rest of the system
needing to change. See [ADR-0001](adr/0001-modular-architecture.md).

### Knowledge graph
A graph of entities (`GraphNode`) and typed relationships (`GraphEdge`) extracted from the
ingested corpus, used by V3's GraphRAG retrieval. In-memory (NetworkX-backed) in the current
implementation, swappable with a Neo4j adapter later. See
[structure.md](architecture/structure.md), `memory/graph/`.

### Manifest
A YAML file describing a complete pipeline configuration — which chunker, embedder,
retriever, reranker, generator, guard, and telemetry backend to use, and with what
parameters. The single source of truth for what's wired into a running pipeline; no
component runs unless it's declared here. See [manifests/_index.md](../manifests/_index.md).

### MG²-RAG
Multi-granularity cross-modal graph — the V5 design for reasoning across text, image, and
table nodes in a single graph structure rather than treating each modality as a separate
index. See [ROADMAP.md](../ROADMAP.md), V5.

### Multi-hop reasoning
Answering a question that requires following more than one relationship (A relates to B,
which relates to C) rather than a single direct match — the reason V3 needs a knowledge
graph instead of only chunk-level retrieval.

### Reciprocal Rank Fusion (RRF)
The parameter-free algorithm that merges two independently ranked result lists (vector +
BM25) into one, using the formula `score(d) = Σ 1/(rrf_k + rank_i(d))`. Chosen because it's
robust to the two lists having incomparable raw score scales. See
[overview.md](architecture/overview.md), section 11.

### Retriever
A component implementing `contracts/retrieval.py`'s `Retriever` Protocol —
`retrieve(query, k) → list[RetrievedChunk]`. Built-in implementations: `BM25Retriever`,
`VectorRetriever`, `HybridRetriever` (which fuses the first two via RRF).

### Trace / TraceStep
The audit record of one pipeline execution. Every retrieval, generation, or agent step
appends a `TraceStep` (name, tokens, latency) to the request's `Trace` via `add_step()`,
which atomically updates running totals. The final `Answer.trace_id` links back to it for
debugging and observability. See [data-model.md](architecture/data-model.md), section 6.

### ULID (Universally Unique Lexicographically Sortable Identifier)
The ID format used for every entity in `core/models/` (`Document.id`, `Chunk.id`,
`Query.id`, etc.) — globally unique like a UUID, but sortable by creation time, which makes
debugging a chronological trace much easier than random UUIDs would.

### VLM (Vision-Language Model)
A generator capable of taking both image and text input (e.g., Claude with vision, GPT-4V),
used in V5 to generate answers grounded in visual evidence (charts, scanned tables) rather
than only extracted text.
