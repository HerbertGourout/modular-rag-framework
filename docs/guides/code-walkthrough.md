# Code Walkthrough — Progressive Reading Guide

**For**: anyone discovering the project who wants to read the code in the right order.
**Principle**: each level goes deeper than the previous one. Read in order; stop when you know
enough for your needs. All paths are clickable from an IDE.
**Updated**: 2026-09-02 (Batch 14 and portable-assurance documentation alignment).

---

## Level 0 — Understand the project in 15 minutes (no code)

| Order | Document | What you learn |
|---|---|---|
| 1 | [docs/onboarding.md](../onboarding.md) | The entry point: the five-phase path and what to read for your profile |
| 2 | [README.md](../../README.md) | What the framework is, pre-alpha status |
| 3 | [docs/guides/framework-overview-onboarding.md](framework-overview-onboarding.md) | Full V1→V5 vision, why it exists |
| 4 | [ROADMAP.md](../../ROADMAP.md) | Where we are **today** (V1.0 checkboxes) |
| 5 | [docs/architecture/capability-matrix.md](../architecture/capability-matrix.md) | Which capabilities are usable, with the evidence |
| 6 | [docs/architecture/overview.md](../architecture/overview.md) | Technical specification |
| 7 | [CHANGELOG.md](../../CHANGELOG.md) | What changed recently |

This guide is phase 4 of that path ("read the code and its rules"); phases 1 and 2 come first.

**The idea in one sentence**: a native reference RAG pipeline plus an engine-neutral boundary,
whose runtime components are Protocol-backed and selected by YAML. Parser dispatch is the explicit exception: file parsers are tried from
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
   - to see guards, tenant isolation, policy engine, redaction, durable feedback/review and audit exercised
     for real, read [security.md](../architecture/security.md) and follow
     `secure-enterprise-rag.yaml` instead of `local-hybrid-rag.yaml`
6. **The answer** — [core/models/answer.py](../../src/modular_rag/core/models/answer.py):
   `Answer` carries the text, the `Citation` list and the `Trace` id.
7. **Post-answer feedback** — [contracts/feedback.py](../../src/modular_rag/contracts/feedback.py)
   and [app/application.py](../../src/modular_rag/app/application.py): `POST /feedback` links a
   caller rating/correction to that trace, enforces tester-role/redaction rules, and stores it
   idempotently. Drift is computed later, offline; it is not another answer stage.

The current LangGraph adapter builds a fixed framework graph. It does not wrap an existing
LangChain/LangGraph application; ADR-0015/Lot 22 plans that future path.

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

## Level 5 — Where to put a change

Each row names the three places a change of that kind touches: where the code goes, how it
becomes reachable at runtime, and which test proves it. Paths are verified against the current
tree.

| I want to add… | Implementation | Wiring | Tests |
|---|---|---|---|
| A new capability contract | `src/modular_rag/contracts/<capability>.py`, exported from [`contracts/__init__.py`](../../src/modular_rag/contracts/__init__.py) | An accepted ADR first (see the contract rule below); then nothing more until an implementation exists | A new `tests/contract/test_<capability>_conformance.py`, parametrized over every implementation |
| A change to an existing contract | The contract file itself | An accepted ADR first (see the contract rule below) | Update the matching `tests/contract/test_*_conformance.py` in the same change |
| A domain component (chunker, retriever, generator, guard…) | The matching domain package, e.g. [`retrieval/retrievers/`](../../src/modular_rag/retrieval/retrievers/) | Register the factory in [`app/default_factories.py`](../../src/modular_rag/app/default_factories.py), then select it by `type:` in a manifest | `tests/unit/<same path>/test_<file>.py`, plus an entry in the capability's conformance test |
| An adapter to an external system | [`adapters/<family>/`](../../src/modular_rag/adapters/), heavy imports inside the method | Same registry-plus-manifest path; `adapters/` never imports a domain module | `tests/unit/adapters/`, and `tests/integration/` when a real service is required |
| A registered type for an existing role | The domain module or adapter above | One `reg.register(role, type, factory)` line in `app/default_factories.py` | The role's conformance test, plus a unit test for the new behaviour |
| A manifest field | [`contracts/manifests.py`](../../src/modular_rag/contracts/manifests.py), where `extra="forbid"` rejects unknown fields | Read it in [`registry.py`](../../src/modular_rag/orchestration/registry.py); add dry-run coverage in [`config_resolution.py`](../../src/modular_rag/app/config_resolution.py) | `tests/unit/contracts/` for the schema, `tests/unit/app/` for validation |
| A CLI command that answers or ingests | A `@app.command()` function in [`cli/__init__.py`](../../src/modular_rag/cli/__init__.py), next to `ingest` and `ask` | Reach the pipeline through `load_application()`, never `RAGEngine` directly | `tests/unit/cli/` |
| A CLI command that inspects or administers | Same file, next to `validate`, `manifest-schema`, `version` and the `db`/`audit`/`feedback`/`review` sub-apps | The narrowest path that does the job — `resolve_manifest()` for schema and validation, an administrative DSN for database and retention commands — never a full application | `tests/unit/cli/` |
| A data or business API route | A route on the `api` object inside `create_app()` in [`api/__init__.py`](../../src/modular_rag/api/__init__.py), next to `/answer`, `/retrieve`, `/feedback` | `Depends(_authenticate)` like its neighbours, with errors mapped through [`api/errors.py`](../../src/modular_rag/api/errors.py) | `tests/unit/api/` |
| An operational probe route | Same file, next to `/health` and `/ready` | **No authentication dependency**: these are deployment probes and are deliberately public; keep the same split | `tests/unit/api/` |
| A new engine adapter | A `DocumentEngine` implementation, e.g. under `adapters/llms/` | `load_engine()` in [`app/bootstrap.py`](../../src/modular_rag/app/bootstrap.py) selects it from `engine.adapter`; declare honestly which controls it cannot honour | [`tests/contract/test_engine_conformance.py`](../../tests/contract/test_engine_conformance.py), which grants an assurance level only on demonstrated behaviour |

Three rules cut across the rows above.

**Every contract change needs an ADR first**, whether you are adding a contract module or
modifying one that exists. [CLAUDE.md](../../CLAUDE.md) §07 states the gate: any new top-level
module, new layer boundary, or contract modification requires a new ADR under `docs/adr/`.
Creating `contracts/<capability>.py` is both.

**Online runtime pipeline components go through the registry and a manifest**, never direct
Python wiring ([ADR-0002](../adr/0002-contracts-and-plugins.md)). [CLAUDE.md](../../CLAUDE.md)
§05 names the exceptions, and they are the only ones: parser dispatch
(`ingestion/pipelines/default.py::_PARSERS`), engine selection (`load_engine`) and API identity
verification (`create_app(token_verifier=...)`). Offline evaluation is outside this rule
entirely — [ADR-0008](../adr/0008-offline-evaluation-and-engine-activation.md) keeps evaluators
and quality gates programmatic, and a manifest that declares them is rejected.

**The layering script gates the dependency direction.** Run
`python scripts/check_layering.py --strict` before assuming an import is allowed.

---

## Verify and extend

- **Validate after a change**: `PATH="$PWD/.venv/bin:$PATH" ./scripts/check.sh quick` (30 s)
  or `full` (unit + contract). Details: [docs/guides/validation.md](validation.md).
- **Check the layer boundaries**: `python scripts/check_layering.py --strict`. The rules it
  enforces are listed in [module-model.md](../architecture/module-model.md); the script is the
  authority when prose and script disagree.
- **Add a component**: follow [CONTRIBUTING.md](../../CONTRIBUTING.md) or the Claude Code skills
  (`/add-retriever`, `/add-generator`, `/add-security-guard`, `/add-component`) — each now
  requires reading the domain digest before any design choice.
