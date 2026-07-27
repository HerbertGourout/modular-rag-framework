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

**The idea in one sentence**: a RAG pipeline where every component (parser, chunker, retriever,
generator, guard…) is a swappable implementation of a Protocol, wired by a YAML manifest —
never by Python code.

---

## Level 1 — The journey of a question (follow this thread first)

Follow a user question all the way to the answer. This is THE walkthrough that makes the whole
framework click. Open the files in this order:

```
mrag ask "…" --manifest manifests/presets/local-hybrid-rag.yaml
```

1. **CLI entry point** — [src/modular_rag/cli/__init__.py](../../src/modular_rag/cli/__init__.py):
   the `ask` command loads the pipeline then calls `pipeline.ask(question)`.
2. **Bootstrap** — [src/modular_rag/app/bootstrap.py](../../src/modular_rag/app/bootstrap.py#L24):
   `load_pipeline()` reads the YAML manifest and asks the registry to build every component.
3. **The manifest** — [manifests/presets/local-hybrid-rag.yaml](../../manifests/presets/local-hybrid-rag.yaml):
   the **source of truth** for wiring: which chunker, which retriever, which weights, which generator.
4. **The registry** — [src/modular_rag/orchestration/registry.py](../../src/modular_rag/orchestration/registry.py)
   and [_default_factories.py](../../src/modular_rag/orchestration/_default_factories.py):
   `type: hybrid` in YAML → factory `HybridRetriever(**cfg.config)`. This is where (and only
   where) new components get registered.
5. **The engine** — [src/modular_rag/orchestration/engine.py](../../src/modular_rag/orchestration/engine.py#L67):
   `RAGEngine._run()` is the conductor. Read it in full (~50 lines); it walks through 5 stages
   in order, each emitting a `TraceStep`:
   - **query guard** → [security/filters/basic_guard.py](../../src/modular_rag/security/filters/basic_guard.py)
     (12 injection patterns across 3 documented families)
   - **retrieval** → [retrieval/retrievers/hybrid.py](../../src/modular_rag/retrieval/retrievers/hybrid.py)
     which queries [vector.py](../../src/modular_rag/retrieval/retrievers/vector.py) (Qdrant) and
     [bm25.py](../../src/modular_rag/retrieval/retrievers/bm25.py), then fuses via
     [fusion/rrf.py](../../src/modular_rag/retrieval/fusion/rrf.py) (weighted RRF)
   - **reranking** → [retrieval/rerankers/cross_encoder.py](../../src/modular_rag/retrieval/rerankers/cross_encoder.py)
   - **generation** → [generation/synthesizers/openai_gen.py](../../src/modular_rag/generation/synthesizers/openai_gen.py)
     or [anthropic_gen.py](../../src/modular_rag/generation/synthesizers/anthropic_gen.py),
     citations built by [citations/builder.py](../../src/modular_rag/generation/citations/builder.py)
   - **answer guard** → the same guard's `check_answer()` (uncited-URL detection)
6. **The answer** — [core/models/answer.py](../../src/modular_rag/core/models/answer.py):
   `Answer` carries the text, the `Citation` list and the `Trace` id.

**Hands-on exercise**: run [examples/hybrid_search/main.py](../../examples/hybrid_search/main.py)
(`python main.py search "…"`) — it prints vector-only, BM25-only and fused results side by side,
which makes RRF fusion concrete. (Needs Qdrant, no LLM key.)

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
   [enrichers/metadata_enricher.py](../../src/modular_rag/ingestion/enrichers/metadata_enricher.py).
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
| `orchestration/` | RAGEngine, registry, router, state machine | [engine.py](../../src/modular_rag/orchestration/engine.py) | — |
| `adapters/` | External bindings (Qdrant, HF, OpenAI…) | [vectorstores/](../../src/modular_rag/adapters/vectorstores/) | `tests/integration/` |
| `eval/` | Exact-match scorers, retrieval metrics | [scorers/](../../src/modular_rag/eval/scorers/) | `tests/unit/eval/` |
| `agents/`, `memory/` | V2/V3 stubs — do not extend in V1 | — | — |

**Mirror convention**: the test for `src/modular_rag/X/Y.py` lives at `tests/unit/X/test_Y.py`.
Reading the test is often the fastest way to understand a file.

---

## Level 4 — The "why": decisions and state of the art

1. **The ADRs** — [docs/adr/](../adr/): 0001 (hexagonal layering), 0002 (contracts + plugins),
   0003 (security & governance), 0004 (strategic features V1-V5).
2. **The research digests** — [docs/research/README.md](../research/README.md): 39 arXiv papers
   distilled into 7 digests. Every design choice in the code cites its digest
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
