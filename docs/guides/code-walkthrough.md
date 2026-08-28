# Code Walkthrough — Progressive Reading Guide

**For**: anyone discovering the project who wants to read the code in the right order.
**Principle**: each level goes deeper than the previous one. Read in order; stop when you know
enough for your needs. All paths are clickable from an IDE.
**Updated**: 2026-07-12 (`feature/v1-sota-alignment` batch).

---

## Level 0 — Understand the project in 15 minutes (no code)

| Order | Document | What you learn |
|---|---|---|
| 1 | [README.md](../../README.md) | What the framework is, pre-alpha status |
| 2 | [docs/guides/framework-overview-onboarding.md](framework-overview-onboarding.md) | Full V1→V5 vision, why it exists |
| 3 | [ROADMAP.md](../../ROADMAP.md) | Where we are **today** (V1.0 checkboxes) |
| 4 | [docs/architecture/overview.md](../architecture/overview.md) | Technical specification |
| 5 | [CHANGELOG.md](../../CHANGELOG.md) | What changed recently |

**The idea in one sentence**: a RAG pipeline whose runtime components are Protocol-backed and
selected by YAML. Parser dispatch is the explicit exception: file parsers are tried from
`ingestion/pipelines/default.py::_PARSERS`, not selected in the manifest.

---

## Level 1 — The journey of a question (follow this thread first)

Follow a user question all the way to the answer. This is THE walkthrough that makes the whole
framework click. Open the files in this order:

```
mrag ask "…" --manifest manifests/presets/local-hybrid-rag.yaml
```

1. **CLI entry point** — [src/modular_rag/cli/__init__.py](../../src/modular_rag/cli/__init__.py):
   the `ask` command loads the pipeline then calls `pipeline.answer(question, tenant_id=...)` —
   **not** `pipeline.ask()`; `answer()` is the real method name on `RAGEngine`.
2. **Bootstrap** — [src/modular_rag/app/bootstrap.py](../../src/modular_rag/app/bootstrap.py#L24):
   `load_pipeline()` reads the YAML manifest and asks the registry to build every component.
   (`load_engine()`/`load_application()` are the entry points that also handle engine-adapter
   selection — see step 5 below.)
3. **The manifest** — [manifests/presets/local-hybrid-rag.yaml](../../manifests/presets/local-hybrid-rag.yaml):
   the **source of truth** for wiring: which chunker, which retriever, which weights, which generator.
4. **The registry** — [src/modular_rag/orchestration/registry.py](../../src/modular_rag/orchestration/registry.py)
   and [app/default_factories.py](../../src/modular_rag/app/default_factories.py) (moved out of
   `orchestration/` in Étape 4 of the ADR-0007 stabilization pass — `orchestration/` may only
   import `core`/`contracts`/`orchestration`, while `app/` is the composition root allowed to
   import concrete adapter implementations):
   `type: hybrid` in YAML → factory `HybridRetriever(**cfg.config)`. This is where (and only
   where) new components get registered.
5. **The engine** — [src/modular_rag/orchestration/engine.py](../../src/modular_rag/orchestration/engine.py):
   `RAGEngine._run_steps()` is the conductor for the native path. A manifest can instead select
   `LangGraphEngineAdapter` via `engine.adapter: langgraph` (see
   [document-engine-contract.md](../architecture/document-engine-contract.md)), but
   `local-hybrid-rag.yaml` uses native, which this walkthrough follows.

   Read it in full — it is **more than 5 fixed stages**. Every step past retrieval runs only if
   its component is configured on the manifest. `local-hybrid-rag.yaml` wires no security or
   governance component, so query/answer guards and governed steps are no-ops for this
   walkthrough. The *complete*, verified sequence — tenant-policy check → policy-engine check →
   guard → retrieve → tenant-filter → rerank → generate → answer guard → redact → human-review →
   audit — lives in [runtime-flow.md](../architecture/runtime-flow.md). Read that file for the
   authoritative step-by-step; the bullet list below only names the pieces most relevant for a
   first read-through:
   - **retrieval** → [retrieval/retrievers/hybrid.py](../../src/modular_rag/retrieval/retrievers/hybrid.py)
     which queries [vector.py](../../src/modular_rag/retrieval/retrievers/vector.py) (Qdrant) and
     [bm25.py](../../src/modular_rag/retrieval/retrievers/bm25.py), then fuses via
     [fusion/rrf.py](../../src/modular_rag/retrieval/fusion/rrf.py) (weighted RRF)
   - **reranking** → [retrieval/rerankers/cross_encoder.py](../../src/modular_rag/retrieval/rerankers/cross_encoder.py)
   - **generation** → [generation/synthesizers/openai_gen.py](../../src/modular_rag/generation/synthesizers/openai_gen.py)
     or [anthropic_gen.py](../../src/modular_rag/generation/synthesizers/anthropic_gen.py),
     citations built by [citations/builder.py](../../src/modular_rag/generation/citations/builder.py)
   - to see guards, tenant isolation, policy engine, redaction, human review and audit exercised
     for real, read [security.md](../architecture/security.md) and follow
     `secure-enterprise-rag.yaml` instead of `local-hybrid-rag.yaml`
6. **The answer** — [core/models/answer.py](../../src/modular_rag/core/models/answer.py):
   `Answer` carries the text, the `Citation` list and the `Trace` id.

**Hands-on exercise**: use [examples/simple_qa/first_query.py](../../examples/simple_qa/first_query.py)
for the current runnable hybrid path. `examples/hybrid_search/main.py` is presently a code sample,
not a working exercise: it accesses the removed `HybridRetriever._bm25` attribute, and its
separate `ingest`/`search` processes cannot retain the in-memory BM25 index.

---

## Level 2 — The journey of a document (ingestion)

```
mrag ingest ./docs --manifest …
```

1. **Ingestion pipeline** — [ingestion/pipelines/default.py](../../src/modular_rag/ingestion/pipelines/default.py):
   `ingest_path()` picks the parser via `parser.supports(path)`.
2. **Parsers** — [ingestion/parsers/](../../src/modular_rag/ingestion/parsers/):
   `text_parser`, `pdf_parser` (pymupdf), `docx_parser`, `html_parser` — all implement the
   [contracts/parsing.py](../../src/modular_rag/contracts/parsing.py) Protocol.
3. **Normalization / enrichment** — [normalizers/text_normalizer.py](../../src/modular_rag/ingestion/normalizers/text_normalizer.py),
   [enrichers/metadata_enricher.py](../../src/modular_rag/ingestion/enrichers/metadata_enricher.py)
   and `ContextualEnricher`, which writes a title-prefixed `embedding_text` while preserving the
   original chunk content for retrieval and citations.
4. **Chunking** — [chunkers/fixed.py](../../src/modular_rag/ingestion/chunkers/fixed.py) and
   [chunkers/adaptive.py](../../src/modular_rag/ingestion/chunkers/adaptive.py): **token-based**
   splitting (512 / 128 overlap, per arXiv:2604.12047) with a merge pass for small fragments
   (arXiv:2603.25333). The shared machinery lives in
   [chunkers/_windowing.py](../../src/modular_rag/ingestion/chunkers/_windowing.py).
5. **Indexing** — back in `engine.ingest_chunks()`: embeddings
   ([adapters/embeddings/](../../src/modular_rag/adapters/embeddings/)) then storage
   ([adapters/vectorstores/](../../src/modular_rag/adapters/vectorstores/)).

---

## Level 3 — Module map (what lives where)

Golden rule ([ADR-0001](../adr/0001-modular-architecture.md)): all dependency arrows point to
`contracts/` + `core/`; domain modules **never** import each other.

| Module | Role | Start with | Tests |
|---|---|---|---|
| `core/` | Pydantic models, enums, errors — imports NOTHING from the project | [models/chunk.py](../../src/modular_rag/core/models/chunk.py), [models/trace.py](../../src/modular_rag/core/models/trace.py) | `tests/unit/core/` |
| `contracts/` | The Protocols (interfaces) for every capability | [__init__.py](../../src/modular_rag/contracts/__init__.py) (lists everything) | `tests/contract/` |
| `ingestion/` | parsers → normalizers → enrichers → chunkers | Level 2 above | `tests/unit/ingestion/` |
| `retrieval/` | BM25, vector, hybrid RRF, rerankers | [retrievers/hybrid.py](../../src/modular_rag/retrieval/retrievers/hybrid.py) | `tests/unit/retrieval/` |
| `generation/` | LLM generators, citations, lexical gate | [synthesizers/openai_gen.py](../../src/modular_rag/generation/synthesizers/openai_gen.py) | `tests/unit/generation/` |
| `security/` | Safety (filters/, redaction/) ≠ Security (policies/) | [filters/basic_guard.py](../../src/modular_rag/security/filters/basic_guard.py) | `tests/unit/security/` |
| `orchestration/` | `RAGEngine`, `ComponentRegistry`, `Container`, `NativeEngineAdapter`, `IndexReconciler`, state machine — **no router**: `QueryRouter`/`FlowCompiler` were removed in Lot 17 | [engine.py](../../src/modular_rag/orchestration/engine.py) | `tests/unit/orchestration/` |
| `adapters/` | External bindings (Qdrant, HF, OpenAI, Keycloak, LangGraph, Postgres…) | [vectorstores/](../../src/modular_rag/adapters/vectorstores/) | `tests/integration/`, `tests/unit/adapters/` |
| `eval/` | Exact-match scorer, retrieval metrics, benchmark runner, quality gate | [scorers/](../../src/modular_rag/eval/scorers/) | `tests/unit/eval/` |
| `agents/` | Engine-delegation adapter-integration only (ADR-0005 §5.2) — no native multi-agent runtime; native prototypes removed in Lot 17 | — | — |
| `memory/` | Key/value storage only (`memory/kv/`) — the graph data model was removed in Étape 8; see [structure.md](../architecture/structure.md#memory--keyvalue-storage-only) | — | — |

**Mirror convention**: the test for `src/modular_rag/X/Y.py` lives at `tests/unit/X/test_Y.py`.
Reading the test is often the fastest way to understand a file.

---

## Level 4 — The "why": decisions and state of the art

1. **The ADRs** — [docs/adr/](../adr/). Read the index in order if you're new — each builds on
   the last:
   - **0001-0003** (hexagonal layering, contracts + plugins, security & governance) — all three
     still accepted, each with a short 2026-08 amendment note where ADR-0005 superseded a
     specific claim.
   - **0004** (strategic features V1-V5) — archived, superseded by 0005.
   - **0005** (document-AI control plane boundary) — the single most important ADR to read if
     you're getting oriented: it's why `agents/`, GraphRAG, fine-tuning execution, and multimodal
     execution are delegated rather than built natively.
   - **0006** — selects LangGraph as the external engine.
   - **0007** — fixes the layer-boundary/manifest-activation gaps that made ADR-0005 real in
     practice.
   - **0008** — separates offline evaluation from online answering and makes engine
     incompatibilities fail startup.
   - **0009** — adds embedder/vector-store dimension reconciliation.
   - **0010-0013** — bounded readiness, PostgreSQL durability/migrations, OTel tracing, and
     operational metrics.
2. **The research digests** — [docs/research/README.md](../research/README.md): the maintained
   paper corpus distilled into topic digests. Design choices should cite the relevant digest
   ([CLAUDE.md](../../CLAUDE.md) coding rule 8); unsourced constants are flagged as such in the
   code (grep for `unsourced`).
3. **Fine-grained traceability** — `git log --oneline`: the 2026-07-12 batch is split into
   atomic commits whose messages explain the what and cite the sources.

---

## Verify and extend

- **Validate after a change**: `PATH="$PWD/.venv/bin:$PATH" ./scripts/check.sh quick` (30 s)
  or `full` (unit + contract). Details: [docs/guides/validation.md](validation.md).
- **Add a component**: follow [CONTRIBUTING.md](../../CONTRIBUTING.md) or the Claude Code skills
  (`/add-retriever`, `/add-generator`, `/add-security-guard`, `/add-component`) — each now
  requires reading the domain digest before any design choice.
