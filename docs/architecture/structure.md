# Complete Structure of the Modular RAG Framework — Exhaustive Explanation

> This document describes every folder and every file of the framework in full detail, with the
> current, real role of each — not an aspirational future role. Where a fact is covered in
> field-by-field depth elsewhere (Pydantic models in
> [data-model.md](data-model.md), the request/ingestion sequence in
> [runtime-flow.md](runtime-flow.md), security pattern counts in [security.md](security.md)),
> this document gives the file-level map and points there rather than maintaining a fourth copy
> of the same detail that can silently drift out of sync — which is exactly what happened to a
> previous version of this document: it described a pre-[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)
> native V2/V3 vision that predates most of what's actually in `src/modular_rag/` today, in
> several places contradicting *itself* (e.g. calling `agents/` a "V2 multi-agent runtime" in one
> section while correctly describing its removal in another). Every claim below was re-verified
> directly against the current source tree.

---

## Overview of the root tree

```
modular-rag-framework/
├── src/                          ← Main source code
│   └── modular_rag/              ← Installable Python package
├── tests/                        ← Test suite (unit, contract, integration, e2e)
├── docs/                         ← Complete technical documentation
├── manifests/                    ← YAML pipeline configurations
├── examples/                     ← Example applications (one complete; see limitations below)
├── benchmarks/                   ← Performance benchmarks (still empty — V3 scope)
├── scripts/                      ← Utility scripts and local audits (layering, docs, licenses…)
├── .claude/                      ← Claude Code skills, hooks, rules, and settings
├── .codex/                       ← Codex project notes
├── .review/                      ← Gitignored, ephemeral Codex review output (not versioned)
├── .gitlab/                      ← Legacy GitLab CI/CD templates (repo now hosted on GitHub)
├── .github/workflows/            ← Current GitHub Actions CI
├── AGENTS.md                     ← Codex instructions and reviewer strategy
├── pyproject.toml                ← Python project configuration
├── requirements-lock.txt         ← `uv pip compile` output; pins exact resolved dependency versions
├── README.md                     ← Pitch, vision, current status, quickstart
├── CLAUDE.md                     ← Instructions for Claude Code
├── CLAUDE.local.example.md       ← Template for local Claude Code preferences
├── ROADMAP.md                    ← V1→V5 milestones, owned vs. delegated split
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
| `pyyaml` | ≥6.0 | YAML manifest loading |
| `httpx` | ≥0.27 | Asynchronous HTTP client |
| `structlog` | ≥24.1 | Structured JSON logging |

Removed in Lot 9 (external plan; not this file's own Lot sequence — see
[docs/guides/dependency-lock.md](../guides/dependency-lock.md)): `pydantic-settings` (the
`app/settings.py` class it backed was already deleted in ADR-0007's Étape 8 — this row used to
carry that same caveat before the dependency was actually removed to match) and `python-ulid`
(`core/ids.py` generates ids via stdlib `uuid.uuid4()`, not ulid — nothing ever imported the
`ulid` package).

**Extras groups (optional dependencies)**

| Group | Command | What it adds |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | FastAPI, Uvicorn, Typer, pymupdf, python-docx, BS4, sentence-transformers, openai, anthropic, qdrant-client, rank-bm25, tiktoken (opt-in subword token counting for chunkers — the default whitespace counter needs no dependency). `cohere` and `langchain-text-splitters` were removed here in Lot 9 — zero imports anywhere, no adapter class ever used either |
| `v4` | `pip install -e ".[v4]"` | opentelemetry-sdk/api/exporter-otlp — wired since ADR-0012 (`adapters/observability/otel_tracing.py`, `observability.tracer.type: otel`) and ADR-0013 (`adapters/observability/otel_meter.py`, `observability.meter.type: otel`) — the same three packages back both the tracing and metrics APIs, no new dependency for ADR-0013 |
| `v5` | `pip install -e ".[v5]"` | pymupdf, pillow, pytesseract (not yet wired into any code — V5 not reached) |
| `langgraph` | `pip install -e ".[langgraph]"` | `langgraph` itself — the external `DocumentEngine` adapter (`adapters/llms/langgraph_engine.py`, ADR-0006, Lot 15). The default native adapter needs none of this; only manifests with `engine.adapter: langgraph` do |
| `postgres` | `pip install -e ".[postgres]"` | `psycopg[binary,pool]` (ADR-0011 — the `pool` extra pulls in the separate `psycopg-pool` package) — durable audit sink and lifecycle ledger implementations (`adapters/audit/postgres_sink.py`, `adapters/lifecycle/postgres_ledger.py`), plus the shared migration runner (`adapters/postgres/migrations.py`), selected by `secure-enterprise-rag.yaml` |
| `auth` | `pip install -e ".[auth]"` | `pyjwt[crypto]` — OIDC/JWKS verification for `adapters/auth/keycloak_verifier.py`, used by authenticated API deployments |
| `supply-chain` | `pip install -e ".[supply-chain]"` | pip-audit, pip-licenses, cyclonedx-bom — CI supply-chain tooling (`scripts/check_licenses.py`, Lot 16b), not needed to run the framework itself |
| `dev` | `pip install -e ".[dev]"` | pytest, pytest-asyncio, pytest-cov, mypy, ruff, httpx, respx, build |
| `all` | `pip install -e ".[all]"` | `v1` + `v4` + `v5` + `langgraph` + `postgres` + `auth` + `dev` (not `supply-chain` — that group is CI/audit tooling, orthogonal to running the framework) |

No `v3` (Graph Memory) group — removed in Lot 17 (`docs/refactoring-plan.md`): its four
dependencies (neo4j, networkx, spacy, python-louvain) had zero imports anywhere in
`src/modular_rag/`, verified before removal, and backed the native GraphRAG traversal/
community-detection build that ADR-0005 §5.2 delegates to the selected external engine instead.

A `requirements-lock.txt` at the repo root pins every resolved dependency to an exact version for
reproducible installs. Generated via `uv pip compile pyproject.toml --python-platform linux
--python-version 3.12 --extra v1 --extra dev --extra langgraph --extra postgres --extra auth -o
requirements-lock.txt` — widened in Lot 9 to also cover `langgraph`, `postgres`, and `auth`, the
exact three extras the Dockerfile installs alongside `v1`, and pinned to the `linux` target
platform since the image runs there regardless of which OS generates the lock.

`pyproject.toml`'s own bounds stay open `>=` ranges by design; the lock file, not the source
bounds, is what a reproducible install actually resolves against. The Dockerfile's runtime stage
now actually consumes this lock (`pip install -c requirements-lock.txt`) instead of resolving
freely against PyPI at build time.

See [docs/guides/dependency-lock.md](../guides/dependency-lock.md) for the full update procedure
and `scripts/check_lock_sync.py` for the CI gate that fails if the Dockerfile's installed extras
ever diverge from what the lock actually covers.

**CLI entry point**: `mrag` → `modular_rag.cli:app` (command installed on the PATH)

**Tool configuration**
- `pytest`: automatic asyncio mode; two custom markers, `integration` (needs Qdrant on
  `localhost:6333`) and `e2e` (needs Qdrant, plus PostgreSQL for a governed/audited preset — an
  LLM API key is only required for an LLM-backed preset, not for the deterministic secure-preset
  scenario)
- `mypy`: strict + pydantic plugin, Python 3.12
- `ruff`: 100 chars per line, Python 3.11 target

---

### `README.md`
Project pitch and reference documentation. Main sections: why this framework exists, current
V1 status and what's proven end-to-end, the six-plane architecture, core-concepts walkthrough,
documentation map, and an FAQ/pitfalls section. Carries a "Pre-alpha" status badge — left as-is
deliberately; whether to change that badge is a business/maintainer decision, not something this
documentation pass makes unilaterally.

---

### `CLAUDE.md`
Architectural instructions for Claude Code. Contains:
- Project purpose and the owned/delegated split per ADR-0005 (block 01)
- Hexagonal layering rules (block 02)
- The 8 coding rules (block 05: contracts first, no cross-domain imports, manifests as source of
  truth, tests mirror `src/`, observability is mandatory, extend rather than rewrite, lazy
  imports for heavy deps, state-of-the-art-first for design decisions)
- Development/validation commands (block 04)
- The V1→V5 roadmap reconciled against the ADRs (block 09)
- The Claude Code workflows exposed by `.claude/skills/`
- The post-edit-quality hook and the layering audit

See also [`docs/guides/claude-code-complete-development-guide.md`](../guides/claude-code-complete-development-guide.md)
for the usage and maintenance guide for this configuration.

### `AGENTS.md`
Persistent instructions for Codex. Defines Codex as the independent reviewer/challenger,
describes the diff-review rules, the editing limits, and the model-tier escalation policy.

### `.codex/`
Codex-specific project notes. The folder stays minimal: durable rules live in
`AGENTS.md`, detailed workflows in `docs/guides/`.

---

### `ROADMAP.md`
Detailed per-version breakdown (V1.0/V1.1/V1.2, V2.0, V2.1, V3.0/V3.1/V3.2, V4.0/V4.1, V5.0),
reconciled with [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)'s owned/delegated
split — the same split [`CLAUDE.md`'s block 09](../../CLAUDE.md#09--roadmap-v1--v5-with-strategic-features)
summarizes. `V2.1` (multi-agent orchestration), `V3.0` (GraphRAG traversal), the fine-tuning
*execution* portion of `V3.2`, and `V5.0` (multimodal VLM execution) are delegated to a selected
external engine (LangGraph, ADR-0006) via the `DocumentEngine` port, not built natively in this
repository at any version — this document previously described those as native build targets
("V2.0 → V2 complete (agents, adaptive routing)"), which no longer matches either ADR-0005's
decision or the actual code.

---

### `CHANGELOG.md`
Keep A Changelog format, tracking additions since v0.0.1.

---

### `CONTRIBUTING.md`
Step-by-step guide for adding a component (example: a new chunker): check the contract →
implement → register in `app/default_factories.py` → select it in a manifest → add tests. PR
checklist included.

---

### `LICENSE`
Apache License 2.0 — Copyright 2026 Publicis Groupe — Data Specialists. Apache 2.0 was chosen
over MIT for the explicit patent clause (enterprise AI/ML standard).

---

## `src/modular_rag/` — THE MAIN PACKAGE

The package follows a strict hexagonal architecture: dependencies only flow downward (`core/`
depends on nothing, `contracts/` depends only on `core/`, domain modules depend only on
`contracts/` + `core/models/`, never on each other). See
[module-model.md](module-model.md) for the complete, exhaustively-verified module tree and
dependency-rule breakdown — the summary below is oriented toward *what each package is for*,
not a repeat of that file-by-file inventory.

```
src/modular_rag/
├── __init__.py              → __version__ reads importlib.metadata (single source: pyproject.toml)
├── core/                    ← Foundation layer — depends on nothing
├── contracts/                ← Interfaces (Protocols) — depends on core/ only
├── adapters/                 ← External bindings — implements contracts/
├── ingestion/                 ← Domain: file → Document → Chunk
├── retrieval/                 ← Domain: Query → list[RetrievedChunk]
├── generation/                 ← Domain: context → Answer
├── security/                   ← Domain: filtering, detection, redaction, policies, audit
├── agents/                     ← Engine-delegation adapter integration only (ADR-0005 §5.2) — no
│                                  native multi-agent runtime; see the dedicated section below
├── memory/                     ← Domain: key/value storage only — no graph data model today
├── eval/                       ← Domain: metrics, benchmarks, regression gating
├── observability/               ← Domain: trace telemetry plus null tracing/metrics adapters
├── orchestration/                ← Runtime: engine, container, registry, native engine, state
│                                    machine, index reconciliation
├── app/                          ← Process-level wiring: bootstrap, application service, config
│                                    resolution
├── cli/                            ← Edge: Typer CLI (`mrag ask`, `mrag ingest`, `mrag version`)
└── api/                             ← Edge: FastAPI REST API
```

---

### `core/` — The foundation layer

**Rule**: `core/` imports nothing from this project. It is the base of everything.

#### `core/enums.py`

Five `StrEnum` enums (values = Python strings, not integers):

| Enum | Values | Usage |
|---|---|---|
| `Modality` | text, image, table, audio, video, code | Content type of a Document/Chunk |
| `RetrievalMethod` | vector, bm25, hybrid | How a `RetrievedChunk` was found |
| `PolicyAction` | allow, deny, redact, warn, require_review | Action of a `PolicyRule` |
| `DataClassification` | public, internal, confidential, restricted | Sensitivity vocabulary (Lot 11a); nothing in the codebase enforces this yet beyond naming it — see [data-classification-policy.md](data-classification-policy.md) |
| `PIICategory` | email, phone, iban, api_key, ssn, credit_card | Canonical PII/secret category names, mirroring `PatternRedactor`'s pattern labels for policy documents and fixtures to reference |

`RetrievalMethod` previously also had `graph`/`multimodal` values, and `core/enums.py` previously
also had `ChunkingStrategy` and `GraphRelation` enums. All were removed together (Étape 8,
[ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md)) — each described a
delegated capability (ADR-0005 §5.2) with zero producing code and zero consumers anywhere in this
codebase, restorable via git history if a native graph/multimodal implementation is ever built.
`RoutingStrategy` and `AgentRole` were removed earlier, in Lot 17, alongside the entire dead
agent/routing/planning prototype cluster they only existed to support (zero real consumers — a
`QueryRouter` used to be constructed in `RAGEngine.__init__` but its `.route()` output was never
actually read anywhere in the pipeline). See
[docs/refactoring/lot-17-prototype-retirement.md](../refactoring/lot-17-prototype-retirement.md).

#### `core/ids.py`
- `new_id()` → ULID (Universally Unique Lexicographically Sortable Identifier, based on UUID4). Sorted by creation time.
- `short_id()` → first 8 characters of the ULID. Used for human-readable labels.

#### `core/document_identity.py`
- `content_hash(content) → str`: stable hash of a document's text, used to detect whether a
  re-ingested document actually changed.
- `document_key(source, tenant_id=None) → str`: the identity key `RAGEngine.ingest()`'s lifecycle
  ledger uses to recognize "the same document" across ingestion runs (Lot 12a idempotency —
  skip-if-unchanged, delete-old-chunks-if-changed).

#### `core/resilience.py`
- `retry_with_backoff(...)`: a generic retry decorator/helper with exponential backoff, for
  wrapping calls to external services.
- `CircuitBreaker` + `CircuitState` (`StrEnum`) + `CircuitBreakerOpenError`: a small circuit-
  breaker implementation — opens after repeated failures, rejecting calls fast instead of
  continuing to hammer a failing dependency, and closes again after a cooldown.

#### `core/errors.py`
Complete exception hierarchy — confirmed current, no drift:

```
ModularRAGError                ← base
├── ConfigurationError         ← invalid manifest or settings
│   └── ManifestError          ← YAML not loadable
├── RegistryError              ← component not found in the registry
├── IngestionError             ← parsing or chunking failed
├── IndexingError              ← vector/lexical store write failed
├── RetrievalError             ← retrieval failed
├── GenerationError            ← LLM call failed
├── SecurityError               ← query or answer blocked
│   ├── PolicyViolationError    ← policy rule violated
│   └── AuthenticationError     ← token verification failed (Lot 11b)
├── EvaluationError             ← scoring or benchmark failed
├── StorageError                ← storage backend failed
└── EngineError                 ← DocumentEngine-level failure (Lot 7)
    ├── EngineTimeoutError
    ├── EngineCancelledError
    └── EngineCapabilityError   ← manifest requires a capability the selected engine doesn't declare
```

`GraphError` and `AgentError` no longer exist — removed in Étape 8 alongside the enum/prototype
cleanup above, for the same reason: nothing in the codebase raised or caught either exception
after the native graph and agent prototypes were removed.

#### `core/models/` — The domain entities

All Pydantic v2 `BaseModel`. No ORM, no DB mapping. Full field-by-field detail, invariants, and
object-lifecycle diagrams live in [data-model.md](data-model.md); this is a one-line-per-model
index:

| Model | File | Frozen? | Role |
|---|---|---|---|
| `Document` | `document.py` | Yes | Atomic ingestion unit; now carries an optional `tenant_id` (Lot 11b) |
| `Chunk` | `chunk.py` | No (mutable, to allow writing `embedding` after creation) | Sub-segment of a Document; also carries `tenant_id`, stamped from the parent Document or an explicit ingestion-call override |
| `Query` | `query.py` | Yes | Immutable user query; carries `tenant_id`. Its former `routing_hint` field was removed in Lot 17 alongside `RoutingStrategy`/`QueryRouter` |
| `RetrievedChunk` | `retrieved.py` | Yes | Chunk + retrieval metadata (`score`, `rank`, `retrieval_method`) |
| `RetrievalResult` | `retrieval_result.py` | — | Return type of `RAGEngine.retrieve()`/`ApplicationService.retrieve()` (ADR-0012): `chunks` + a real framework `trace_id` |
| `Citation` / `Answer` | `answer.py` | — | Generated text, citations, and traceability metadata |
| `TraceStep` / `Trace` | `trace.py` | — | Per-step performance metrics, accumulated via `Trace.add_step()`. `Trace.routing_strategy` **no longer exists** — it was removed in Étape 8 (`TRACE_SCHEMA_VERSION` bumped `"1.1"` → `"1.2"` specifically for this), not merely left unset as an earlier pass through this documentation mistakenly concluded; see [data-model.md](data-model.md) for the full, current field table |
| `PolicyRule` / `Policy` | `policy.py` | — | A policy rule (`condition`, `action`, `priority`) grouped under a `Policy` scoped to a tenant. **Not V4-only** — `PolicyEngine` (see the `security/` section below) is wired into the live request path today, not a future feature |
| `Metrics` | `metrics.py` | — | 16-field evaluation-score bag, grouped into retrieval / answer / policy / cost-latency / failure-signal families; see [data-model.md](data-model.md#metrics) for the complete field table and `summary()`'s exact exclusion behavior |

---

### `contracts/` — The framework interfaces

**Rule**: All `Protocol`s are `@runtime_checkable`. No concrete class inherits from these
Protocols — conformance is structural (duck typing verified at runtime via
`isinstance(obj, Protocol)`). Every file below is re-exported from `contracts/__init__.py`
(confirmed by direct read — the list is exhaustive, nothing is missing from it):

| File | Exported name(s) | Role |
|---|---|---|
| `chunking.py` | `Chunker` | `chunk(doc) → list[Chunk]` |
| `embeddings.py` | `Embedder` | `embed(texts) → list[list[float]]`, `aembed()`, `dimensions` |
| `retrieval.py` | `Retriever` | `retrieve(query, k) → list[RetrievedChunk]`, `aretrieve()` |
| `generation.py` | `Generator` | `generate(query, context, trace) → Answer`, `agenerate()` |
| `reranking.py` | `Reranker` | `rerank(query, chunks, k) → list[RetrievedChunk]` |
| `security.py` | `SecurityGuard`, `Redactor`, `GuardResult`, `TenantPolicy` | `check_query()`, `check_answer()`, `redact()`; `TenantPolicy` is the fail-closed tenant-isolation contract (`enforce_query`, `enforce_ingest`, `filter_chunks`) |
| `evaluation.py` | `Evaluator`, `AnswerEngine` | `evaluate(query, answer, expected, context) → Metrics` |
| `indexing.py` | `Indexer`, `VectorIndexer` | `Indexer`: generic `index()`/`delete()`/`clear()`. `VectorIndexer` (ADR-0009): the vector-specific sub-protocol adding `retrieve_by_vector()`, so a vectorstore adapter can be conformance-tested without requiring the retrieval-side `Retriever` protocol too |
| `storage.py` | `Storage` | `put(key, value)`, `get(key)`, `delete(key)`, `exists(key)` |
| `telemetry.py` | `Telemetry` | `record_trace(trace)`, `record_metrics(metrics)` |
| `manifests.py` | `ManifestLoader`, `PipelineManifest`, `ComponentConfig`, `EngineSelection`, `GovernanceSection`, `ObservabilitySection`, `QualitySection` | The complete YAML manifest schema — see below |
| `engine.py` | `DocumentEngine`, `EngineCapability`, `EngineRequest`, `EngineResult`, `EngineStep`, `ExecutionContext`, `GovernanceDecision`, `GovernanceHook`, `CancellationToken` | The port that lets a manifest select either the native pipeline (`NativeEngineAdapter`) or an external engine (`LangGraphEngineAdapter`) interchangeably — see [document-engine-contract.md](document-engine-contract.md) and [runtime-flow.md](runtime-flow.md) |
| `identity.py` | `TenantContext`, `TokenVerifier` | Verified-caller identity contract; `TokenVerifier.verify(token) → TenantContext`, implemented by `adapters/auth/keycloak_verifier.py` |
| `audit.py` | `AuditEvent`, `AuditEventType`, `AuditSink`, `ALLOWED_PAYLOAD_KEYS`, `AUDIT_SCHEMA_VERSION` | Compliance-audit event contract (Lot 10); `ALLOWED_PAYLOAD_KEYS` is a Pydantic-validator-enforced allowlist blocking arbitrary keys from ending up in an audit payload |
| `lifecycle.py` | `LifecycleLedger`, `DocumentRecord`, `DocumentStatus` | Document re-ingestion idempotency (Lot 12a) — "have I seen this exact content from this source+tenant before?" |
| `reconciliation.py` | `DocumentDivergence`, `ReconciliationReport`, `RepairResult` | Vector/lexical index-divergence detection and repair (Lot 12b), implemented by `orchestration/reconciliation.py`'s `IndexReconciler` |
| `erasure.py` | `ErasureProof` | Right-to-erasure evidence returned by `RAGEngine.erase_document()` |
| `review.py` | `ReviewItem`, `ReviewQueue` | Human-in-the-loop review queue contract, implemented by `security/policies/human_review.py`'s `HumanReviewGate` |
| `secrets.py` | `SecretResolver` | `resolve(reference) → str`; implemented by `app/config_resolution.py`'s `EnvSecretResolver`, resolving `secret://VAR_NAME` references in a manifest |
| `parsing.py` | `Parser` | `supports(path) → bool`, `parse(path) → Document` |

**`PipelineManifest`** is the complete schema of a YAML manifest — a `ComponentConfig` per role
(chunker, embedder, indexer, retriever, reranker, generator, guard, evaluator, telemetry, plus
`governance.*` and `quality.*` sub-sections) and an optional `engine: EngineSelection` field that
picks the `DocumentEngine` adapter (native by default, `langgraph` when set). `planning.py`
(`Planner`/`ExecutionPlan`/`ExecutionStep`) and `agents.py` (`Agent`/`AgentTask`/`AgentResult`) —
Protocols for a native multi-agent runtime — no longer exist; they backed the same dead prototype
cluster covered under `agents/` below and were removed in Lot 17.

---

### `adapters/` — External bindings

**Role**: isolate heavy external dependencies so a domain module never needs one installed to be
unit-tested. Adapters import `contracts/` + `core/` + external libraries, never a domain module.

#### `adapters/embeddings/`

- **`openai_embedder.py` → `OpenAIEmbedder`**: implements `Embedder`. Lazy import of `openai`.
- **`hf_embedder.py` → `HuggingFaceEmbedder`**: implements `Embedder`. Lazy import of
  `sentence-transformers`; `aembed()` runs the synchronous model in a thread-pool executor.
- **`deterministic_embedder.py` → `DeterministicEmbedder`**: feature-hashing embedder with no
  external dependency and no network call, built for reproducible e2e tests that don't require an
  LLM API key (`tests/e2e/manifests/secure-deterministic-rag.yaml`).

#### `adapters/vectorstores/`

**`qdrant_store.py` → `QdrantStore`**: implements `VectorIndexer`. Lazy import of `qdrant-client`.
- `_ensure_collection()`: creates the Qdrant collection if it doesn't exist, and validates an
  *existing* collection's vector configuration against this store's embedder dimension before any
  upsert (ADR-0009) — catching a dimension/named-vector mismatch early with a clear error instead
  of a confusing failure mid-upsert.
- `index(chunks)`: upserts `PointStruct`s with vector + full payload, including `tenant_id`.
- `retrieve_by_vector(vector, k, tenant_id=None)`: `client.search()` with an optional Qdrant
  payload `FieldCondition` filter on `tenant_id` — cross-tenant points are excluded *at query
  time* when a `tenant_id` is given (Lot 12b), not merely filtered after the fact.
- `retrieve(query, k)`: still raises `NotImplementedError` — the bare `Retriever`-shaped call
  needs an `Embedder` to turn `query.text` into a vector first; `retrieval/retrievers/vector.py`'s
  `VectorRetriever` is the component that actually wires an embedder in front of this store.

#### `adapters/llms/`

**`langgraph_engine.py` → `LangGraphEngineAdapter`**: implements `DocumentEngine`. This is a real,
substantial adapter, not a placeholder — a `StateGraph` (route → retrieve → guard → generate/
blocked → END) that reproduces the native pipeline's tenant-isolation and redaction behavior
inside LangGraph nodes. See [runtime-flow.md](runtime-flow.md)'s "Engine delegation" section for
the full node-by-node breakdown, including a documented historical bug (a query with no
`tenant_id` used to bypass tenant filtering here, found and fixed during Lot 18's pilot
comparison) and what this adapter deliberately does not replicate (audit-sink emission,
human-review queueing — those stay above the `DocumentEngine` boundary).

#### `adapters/auth/`

**`keycloak_verifier.py` → `KeycloakTokenVerifier`**: implements `TokenVerifier` (Lot 11b). OIDC/
JWKS-based bearer-token verification against a configured Keycloak realm, returning a
`TenantContext` (`tenant_id`, `user_id`, `roles`). This directory is no longer a `.gitkeep`
placeholder.

#### `adapters/audit/`

**`postgres_sink.py` → `PostgresAuditSink`**: implements `AuditSink`. Lazy import of `psycopg`/
`psycopg_pool`. Durable, append-only audit-event storage — the production counterpart to
`InMemoryAuditSink` (`security/audit/store.py`, see below), selected by
`secure-enterprise-rag.yaml`. Since ADR-0011: connection pooling (`psycopg_pool.ConnectionPool`,
replacing a single cached connection), `purge_expired()`/`count_expired()` for
`AuditEvent.retention_days` enforcement (fail-closed behind an `allow_purge` constructor flag —
see `docs/guides/postgres-permissions.md` for the DB-role separation this pairs with), and an
opt-in `auto_migrate` flag routing through `adapters/postgres/migrations.py` instead of the
inline schema-creation this adapter used to run unconditionally on every connect.

#### `adapters/lifecycle/`

**`postgres_ledger.py` → the Postgres-backed `LifecycleLedger`**: implements `LifecycleLedger`.
Durable counterpart to `ingestion/lifecycle/in_memory_ledger.py`'s `InMemoryLifecycleLedger`,
tracking document re-ingestion idempotency (Lot 12a) across process restarts. Since ADR-0011:
the same connection-pooling and `auto_migrate` changes as `postgres_sink.py` above.

#### `adapters/postgres/`

**`migrations.py` → `MigrationRunner`** (ADR-0011): a shared, non-adapter infrastructure helper
(no Protocol — same "operates on already-Protocol'd things" reasoning as
`orchestration/reconciliation.py`'s `IndexReconciler`) both Postgres adapters above import for
schema management. `.migrate()`/`.rollback()`/`.applied_versions()` against a `schema_migrations`
tracking table it creates and owns; a `pg_advisory_xact_lock` on a dedicated, non-autocommit
connection guards concurrent callers. The paired `.up.sql`/`.down.sql` migration files live in
`sql/` inside this same subpackage (not a repo-root `migrations/` directory — that would not ship
in the built wheel), resolved via `importlib.resources` so this works identically from a dev
checkout and an installed package. Exposed via `mrag db migrate`/`rollback`/`status`
(`--dsn`, never `--manifest` — see `docs/guides/postgres-permissions.md`'s `migration_role`).

#### `adapters/graphstores/`, `adapters/search/`

**Current state: `.gitkeep` only**, unchanged. These remain reserved engine-delegation adapter
targets — `graphstores/` for a GraphRAG-capable external engine's backing store, `search/` for a
multi-provider web-search adapter (Tavily, Brave, …) — neither built yet.

---

### `ingestion/` — Document processing pipeline

**Flow**: `File → Parser → TextNormalizer → MetadataEnricher → Chunker → ContextualEnricher →
list[Chunk]`, then (as a separate, caller-made call — see [runtime-flow.md](runtime-flow.md))
`RAGEngine.ingest_chunks(chunks)` embeds and indexes them.

#### `ingestion/parsers/`

- **`text_parser.py` → `TextParser`**: `.txt`, `.md`, `.rst` — UTF-8 read with error replacement.
- **`pdf_parser.py` → `PDFParser`**: `.pdf`, lazy import of `fitz` (PyMuPDF).
- **`docx_parser.py` → `DocxParser`**: `.docx`, lazy import of `python-docx`.
- **`html_parser.py` → `HTMLParser`**: `.html`/`.htm`, lazy import of `beautifulsoup4`.

#### `ingestion/normalizers/`

**`text_normalizer.py` → `TextNormalizer`**: `normalize(doc) → Document` (new instance — Document
is frozen). NFKC unicode normalization, collapses 3+ newlines to 2 and 2+ spaces to 1, strips.

#### `ingestion/enrichers/`

**`metadata_enricher.py` → `MetadataEnricher`**: `enrich(doc) → Document` (new instance). Adds
`filename`, `extension`, `size_bytes`, `enriched_at` to metadata. Runs on the `Document`, before
chunking.

**`contextual_enricher.py` → `ContextualEnricher`**: `enrich(doc, chunks) → list[Chunk]` (new
instances). Runs after chunking — sets each chunk's `embedding_text` to
`f"Document: {title}\n\n{content}"` (`title` from `Document.metadata["filename"]`, falling back
to `Document.source`), which `RAGEngine.ingest_chunks()` embeds instead of `content`. `content`
itself is never touched, so citations and `/retrieve` see the original text unprefixed. A cheap,
deterministic approximation of "contextual retrieval" — no arXiv citation backs this specific
technique in `docs/research/DIGEST-chunking.md`/`DIGEST-retrieval.md`; see the class's own
docstring for why an LLM-generated per-chunk summary (the fuller industry technique) was
deliberately not used.

#### `ingestion/chunkers/`

- **`fixed.py` → `FixedSizeChunker`**: sliding window over words/tokens, tracks `start_char`/
  `end_char` in the original document.
- **`adaptive.py` → `AdaptiveChunker`**: splits first on Markdown headings and blank lines;
  sections too large are re-split with fixed-size logic.
- **`_windowing.py`** (private, shared by both): `window_by_tokens()`, `merge_small_spans()`,
  `iter_sections()`, plus a pluggable `TokenCounter` abstraction (`resolve_token_counter()`) — a
  whitespace-based counter by default, an optional `tiktoken`-backed counter when a manifest sets
  `token_counter: "tiktoken"`.

#### `ingestion/lifecycle/`

New subpackage (Lot 12a), not covered in a previous version of this document:
- **`hashing.py`**: content-hashing helpers backing the lifecycle ledger's change-detection.
- **`in_memory_ledger.py` → `InMemoryLifecycleLedger`**: implements `LifecycleLedger`; the default,
  reference implementation.
- **`backup.py` → `backup_ledger()` / `restore_ledger()`**: JSON export/import of ledger state, one
  of the rollback surfaces documented in `docs/guides/backup-restore.md`.

#### `ingestion/pipelines/default.py`

- **`ingest_path(path, chunker, tenant_id=None) → list[Chunk]`**: detects the right parser, runs
  parser → normalizer → enricher → tenant_id override → chunker. A given `tenant_id` always wins
  over whatever the parsed `Document` already carries.
- **`ingest_directory(directory, chunker, tenant_id=None) → list[Chunk]`**: recursively walks the
  directory, calling `ingest_path` on every supported file with the same `tenant_id`.

Neither function embeds or indexes anything — that is `RAGEngine.ingest_chunks()`'s job, called
separately by the caller. See [runtime-flow.md](runtime-flow.md) for why this is two calls, not
one, and for the confirmed per-chunk (not batched) embedding loop inside `ingest_chunks()`.

---

### `retrieval/` — Search engine

#### `retrieval/retrievers/`

- **`bm25.py` → `BM25Retriever`**: implements `Retriever`. Lazy import of `rank-bm25`. In-memory
  index, rebuilt from scratch on every new process — this is why `HybridRetriever` can silently
  degrade to vector-only immediately after a restart, until `index()` is called again.
- **`vector.py` → `VectorRetriever`**: implements `Retriever`. Embeds the query via an injected
  `Embedder`, then calls the injected vector store's `retrieve_by_vector()`. Both dependencies are
  injected post-construction by `orchestration/registry.py`'s `wire()` — the retriever itself
  never instantiates an adapter.
- **`hybrid.py` → `HybridRetriever`**: combines `VectorRetriever` + `BM25Retriever` via Reciprocal
  Rank Fusion; labels results `RetrievalMethod.HYBRID` only when both sources actually contribute,
  `VECTOR` or `BM25` otherwise.

#### `retrieval/fusion/rrf.py`

**`reciprocal_rank_fusion(lists, k=10, rrf_k=60, weights=None) → list[RetrievedChunk]`**: pure
function, `score(d) = Σ weight_i / (rrf_k + rank_i(d))`. Weights default to `1.0` per list.
Deduplicates by `chunk.id`, limits to `k`, renumbers ranks 1..N.

#### `retrieval/rerankers/`

**`cross_encoder.py` → `CrossEncoderReranker`**: lazy import of `sentence-transformers`, default
model `cross-encoder/ms-marco-MiniLM-L-6-v2`. Pairs `(query.text, chunk.content)`, scores via
`model.predict()`, sorts.

#### `retrieval/planners/`

**Current state: `.gitkeep` only.** A previous version of this document described real
`SimplePlanner`/`GraphPlanner` classes here — neither exists in the current source tree. This
directory is an unused stub, not a built feature; retrieval strategy selection today happens
entirely through manifest-driven component wiring (which concrete `Retriever` a manifest selects),
not a separate planning step.

---

### `generation/` — Answer synthesis

#### `generation/synthesizers/`

- **`openai_gen.py` → `OpenAIGenerator`**: implements `Generator`. Lazy import of `openai`. Default
  `model="gpt-4o-mini"`, `temperature=0.1`, `max_tokens=2048`. Builds a numbered prompt (`[1]`,
  `[2]`…), calls the API, builds citations, emits a `TraceStep` with token counts. `agenerate()` is
  the async counterpart.
- **`anthropic_gen.py` → `AnthropicGenerator`**: implements `Generator`. Lazy import of
  `anthropic`. Default `model="claude-opus-4-7"`, `max_tokens=2048`. Same structure as
  `OpenAIGenerator`, via the Anthropic Messages API.
- **`deterministic_gen.py` → `DeterministicGenerator`**: builds the answer text directly from
  citation passages (no LLM call), guaranteeing citation-text agreement for reproducible e2e
  tests that need no LLM API key.

#### `generation/citations/builder.py`

**`build_citations(chunks) → list[Citation]`**: pure function, one `Citation` per chunk, `passage`
truncated to 300 chars.

#### `generation/validators/groundedness.py`

**`GroundednessValidator`**: `validate(answer, context) → float [0,1]` — ratio of answer tokens
present in the context (case-insensitive word-set intersection).

---

### `security/` — Defense in depth

This section summarizes each file's role; the exact pattern counts, risk-score tables, and
research citations behind the guard/redactor design live in [security.md](security.md) — kept in
sync with this exact source this same documentation pass, after finding and fixing the same class
of stale-pattern-count errors this file used to repeat.

#### `security/filters/basic_guard.py` → `BasicSecurityGuard`

Implements `SecurityGuard`. `check_query()` checks 12 injection-style regex patterns across three
research-cited families plus a blocked-terms list. `check_answer()` is a real, shipped check (not
a pass-through) — it flags any URL in the answer text that isn't backed by a citation, a
corpus-poisoning defense. See [security.md](security.md) for the full pattern tables and the
arXiv citations behind each family.

#### `security/detectors/adversarial.py` → `AdversarialDetector`

A real, functioning class (three exfiltration-pattern regexes, `risk_score=0.95` on a match) —
but **not registered in `app/default_factories.py` under any type name**, so no manifest can
select it today. Its own docstring labels it `(V4)`. Listed here for completeness, not as an
available control — see [security.md](security.md)'s "Components that exist but aren't wired"
section.

#### `security/redaction/patterns.py` → `PatternRedactor`

Implements `Redactor`. Seven substitutions total: six named regex patterns (`email`,
`phone_fr_local`, `phone_fr_intl`, `iban`, `api_key`, `ssn_us`) plus a separate Luhn-validated
card-number check. FR/US-specific pattern coverage; opt-in per manifest, not mandatory.

#### `security/policies/policy_engine.py` → `PolicyEngine`

Implements no single Protocol directly but is the concrete class a manifest's
`governance.policy_engine` selects. **Wired into the live request path today** —
`RAGEngine._run_steps()` calls `policy_engine.enforce_query(query)` unconditionally whenever one
is configured — not a V4-only or dormant feature, contrary to what a previous version of this
document (and, until this pass, [threat-model.md](threat-model.md)) claimed. `enforce_query()`
evaluates enabled policies in descending priority order; a `DENY` raises
`PolicyViolationError`, and a `PolicyEngine` failure itself is deny-by-default (Lot 11b), never
allow-by-default. Rule conditions are currently plain case-insensitive substring matches
(extensible toward CEL/OPA Rego in V4, per the class's own docstring — the substring matching is
real and shipped now, the extensibility is future work).

#### `security/policies/tenant_isolation.py` → `TenantIsolationPolicy`

Implements `TenantPolicy` (Lot 11b) — not present in a previous version of this document at all,
despite being one of the most load-bearing security components in the codebase. Fail-closed:
`enforce_query()`/`enforce_ingest()` raise `SecurityError` for a missing/mismatched `tenant_id`
against a tenant-isolated manifest, and `filter_chunks()` strips any retrieved chunk whose
`tenant_id` doesn't match the query's — a belt-and-suspenders post-filter on top of
`QdrantStore`'s own query-time `tenant_id` filter.

#### `security/policies/human_review.py` → `HumanReviewGate`

Implements `ReviewQueue` (Lot 11c) — also missing from a previous version of this document. Holds
high-risk answers for human sign-off before they're released, per `PolicyAction.REQUIRE_REVIEW`.

#### `security/audit/store.py` → `InMemoryAuditSink`

Implements `AuditSink` (Lot 10) — the reference, non-durable counterpart to
`adapters/audit/postgres_sink.py`'s `PostgresAuditSink`.

---

### `agents/` — engine-delegation adapter integration (per ADR-0005 §5.2)

**Removed in Lot 17** (`docs/refactoring-plan.md`): five pre-ADR-0005 native agent
prototypes used to live here — `CoordinatorAgent`, `RetrieverAgent`, `ExtractorAgent`,
`SynthesizerAgent`, `ValidatorAgent` — each with zero test coverage and zero consumers
anywhere in the codebase (verified via a full dependency search before removal). They
implemented exactly the generic multi-agent orchestration capability
[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2 delegates to the selected
external engine, predating that decision. The directory now holds only `__init__.py`
(docstring pointing here) and empty subdirectory stubs (`.gitkeep`), reserved for actual
adapter-integration code that calls the external engine — not yet built. Restoration path:
git history. See
[docs/refactoring/lot-17-prototype-retirement.md](../refactoring/lot-17-prototype-retirement.md).

---

### `memory/` — Key/value storage only

**`memory/kv/in_memory.py` → `InMemoryStorage`**: implements `Storage`. Plain Python dict. Not
thread-safe, for dev/tests only.

**`memory/graph/` no longer exists.** `KnowledgeGraph`/`GraphNode`/`GraphEdge`
(`memory/graph/knowledge_graph.py`) were **removed in Étape 8**
([ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md), "Resolved:
knowledge-graph data model"): `neighbours()`/`subgraph_for_query()` were genuine multi-hop-
traversal logic — exactly the GraphRAG capability ADR-0005 §5.2 delegates to the external
engine — and the module had zero consumers anywhere outside its own test. Lot 17 had previously
kept it with an explicit "undecided" caveat; Étape 8 resolved that decision by removing it,
restorable via git history if a real, wired consumer ever emerges. `core.enums.GraphRelation`
was removed alongside it.

`memory/versioning/graph_versioning.py` (`GraphVersionManager`, EvoRAG edge reinforcement) was
**removed in Lot 17** — zero test coverage, zero consumers, and squarely in the delegated
fine-tuning-execution territory ADR-0005 §5.2 assigns to the external engine. Both `memory/graph/`
and `memory/versioning/` are `.gitkeep`-only today.

---

### `eval/` — Evaluation

- **`eval/scorers/exact_match.py` → `ExactMatchEvaluator`**: implements `Evaluator`.
  Precision/Recall/F1 over token sets, case-insensitive. `expected=None` → all-`None` `Metrics`.
- **`eval/scorers/retrieval_metrics.py`**: pure functions `recall_at_k()`, `precision_at_k()`,
  `mrr()`; `compute_retrieval_metrics()` aggregates them into a `Metrics`.
- **`eval/runners/benchmark.py` → `BenchmarkCase` + `BenchmarkReport` + `BenchmarkRunner`**: walks
  a list of question/expected-answer/relevant-chunk-id cases through `engine.answer()`, computing
  metrics and aggregate averages.
- **`eval/quality_gate.py` → `QualityGate`** (+ `GateMode`, `GateViolation`, `GateResult`,
  `QualityGateError`): a regression gate — evaluates a `Metrics` result against configured
  thresholds and raises/reports a violation on drop, the mechanism `docs/refactoring-plan.md`
  refers to as preventing merges on an F1 regression. Not present in a previous version of this
  document.

---

### `observability/`

**`StructlogTelemetry`**: implements `Telemetry`. Structured JSON logs via structlog.

**`NullTelemetry`**: implements `Telemetry`. No-op for tests (zero overhead).

**`NullTracer` / `NullSpan`**: no-op implementations of the live span contract. The real
OpenTelemetry adapter lives under `adapters/observability/otel_tracing.py`.

**`NullMeter`**: no-op implementation of operational counters, histograms and gauges. The real
OpenTelemetry adapter lives under `adapters/observability/otel_meter.py`.

---

### `orchestration/` — Runtime engine

#### `orchestration/engine.py` → `RAGEngine`

The native pipeline's conductor. Public surface is considerably larger than "ingest, answer,
retrieve":

| Method | Role |
|---|---|
| `ingest(documents)` | Full lifecycle-ledger-aware ingestion: skip if content unchanged, delete old chunks if changed, chunk → `ingest_chunks()` → record in the ledger (Lot 12a idempotency) |
| `ingest_chunks(chunks)` | Embeds **one chunk at a time** (not batched — see [runtime-flow.md](runtime-flow.md)) and indexes; enforces `tenant_policy.enforce_ingest()` per chunk |
| `delete_document(document_key)` | Removes a previously-ingested document's chunks and ledger record |
| `rebuild_document(document)` | Re-ingests a document "from scratch" (used by the rebuild-from-source recovery path) |
| `erase_document(document_key)` | Right-to-erasure: deletes chunks + ledger record, returns an `ErasureProof` |
| `answer(question, **kwargs)` | The full governed query path — see the table below |
| `retrieve(question, k, tenant_id=None)` | Retrieval only, tenant-filtered, no generation |
| `manifest_id`, `tenant_policy_active`, `chunker`, `retriever` | Public read-only properties (Lot 8 — `api/`/`cli/` no longer reach into the private `Container`) |
| `close()` | Releases any held resources (e.g. a Postgres connection pool) |

`answer()`'s real internal sequence (`_run_steps()`, confirmed directly against the source) is
considerably more than the five-step version a previous edition of this document described:
tenant-policy fail-closed check → policy-engine check → guard query check → retrieve → tenant-
policy chunk filter → optional rerank → generate → guard answer check → optional redaction →
optional human-review hold → audit + telemetry recording. Every step past retrieval is optional
and only runs when the corresponding component is configured in the manifest. See
[runtime-flow.md](runtime-flow.md) for the full sequence diagram and the double-audit-event
behavior on a denial.

#### `app/default_factories.py`
Application composition root for all built-in components. `create_default_registry()` creates a
generic `ComponentRegistry` and calls `register_defaults(reg)`; `orchestration/` itself never
imports a concrete domain or adapter implementation directly.

#### `orchestration/registry.py` → `ComponentRegistry`
Maps `(role, type_name)` → factory callable.
- `register(role, type_name, factory)`: adds a factory.
- `wire(manifest) → Container`: for each role in the manifest, calls `factory(config)`, stores the
  result in the `Container`.
- No built-in/default classmethod — concrete catalogue ownership stays entirely in `app/`.

#### `orchestration/container.py` → `Container`
The DI container itself lives here, **not** in `app/container.py` — it moved during Étape 8 of
the ADR-0007 stabilization pass. `app/container.py` still exists, but only as a 5-line
backward-compatibility re-export shim: `from modular_rag.orchestration.container import
Container`. A caller importing `from modular_rag.app.container import Container` still works, but
the real class definition is under `orchestration/`.

#### `orchestration/native_engine.py` → `NativeEngineAdapter`
Implements `DocumentEngine`, wrapping `RAGEngine` behind the same port `LangGraphEngineAdapter`
implements — its declared capability set is empty, since the native pipeline doesn't offer
streaming/cancellation/governance-intercept the way the LangGraph adapter does. This is what a
manifest with no `engine:` section (or `engine.adapter: native`) resolves to.

#### `orchestration/reconciliation.py` → `IndexReconciler`
Implements the reconciliation contract (`contracts/reconciliation.py`, Lot 12b) — detects
divergence between the vector index and the lexical (BM25) index or the lifecycle ledger, and can
repair it, rather than letting the two silently drift apart.

`orchestration/router.py` (`QueryRouter`) and `orchestration/flow_compiler.py`
(`FlowCompiler`) were **removed in Lot 17**. Both were part of the same dead prototype cluster as
`agents/`'s five classes: `RAGEngine` used to construct a `QueryRouter` in `__init__` but never
called `.route()` on it anywhere in the actual pipeline. `FlowCompiler.compile()` had zero callers
at all. The routing role either would have played is filled today by `app/bootstrap.py`'s
`load_engine()` (Lot 15) selecting a `DocumentEngine` adapter directly from the manifest, with no
compiler class in between. See
[docs/refactoring/lot-17-prototype-retirement.md](../refactoring/lot-17-prototype-retirement.md).

#### `orchestration/state_machine.py` → `PipelineStateMachine`
States: `IDLE → GUARDING_QUERY → RETRIEVING → RERANKING → GENERATING → GUARDING_ANSWER →
EVALUATING → DONE` (+ `ERROR`). Hard-coded transition matrix; `transition(to)` validates and logs
every state change.

---

### `app/` — Process-level wiring

#### `app/settings.py` → deleted (Étape 8, ADR-0007)
This file declared a `MRAG_`-prefixed `Settings` (pydantic-settings) class — but it was
orphaned: nothing in the real pipeline-wiring path (`app/default_factories.py`,
`app/bootstrap.py`) ever constructed `Settings()` or called `get_settings()`, so none of its
`MRAG_*` fields ever had any effect on a running pipeline. Found in Lot 16c, confirmed dead, and
deleted outright in Étape 8 (see
[docs/adr/0007-layer-boundaries-and-control-plane-activation.md](../adr/0007-layer-boundaries-and-control-plane-activation.md)) —
not deprecated, since a pre-alpha codebase with zero real consumers has nothing to keep
backward-compatible. The working credential env vars are, and always were, the LLM SDKs' own
standard names — `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` — read only when the manifest's
`generator.config.api_key` is left unset. There is no `MRAG_QDRANT_URL`-style env-var fallback for
vectorstore config either: `url`/`collection` must be set directly in the manifest's
`indexer`/`retriever` `config:` block. See [docs/guides/deployment.md](../guides/deployment.md).

#### `app/container.py`
Compatibility shim only — see `orchestration/container.py` above for the real class.

#### `app/config_resolution.py`
- **`EnvSecretResolver` → implements `SecretResolver`**: resolves `secret://VAR_NAME` references
  in a manifest against environment variables.
- **`resolve_manifest(path, resolver=None) → PipelineManifest`**: reads the YAML, interpolates
  `${VAR}`/`secret://` references, validates via Pydantic.
- **`interpolate()` / `_interpolate_value()`**: the recursive interpolation walk.
- **`validate_capabilities(manifest, registry) → list[str]`**: checks a manifest's requirements
  against what the selected `DocumentEngine` adapter actually declares, returning any gaps.
- **`migrate_v1_to_v2()` / `rollback_v2_to_v1()`**: manifest-schema migration helpers.

#### `app/bootstrap.py`
- `load_manifest(path) → PipelineManifest`: thin wrapper reading + validating the YAML.
- `load_pipeline(path) → RAGEngine`: `resolve_manifest()` → `create_default_registry()` →
  `registry.wire(manifest)` → `RAGEngine(container)` — the native-pipeline entry point.
- `load_engine(path) → DocumentEngine`: resolves the manifest's `engine.adapter` field and returns
  either a `NativeEngineAdapter` or a `LangGraphEngineAdapter` — the entry point `api/`/`cli/`
  actually use once engine delegation is in play (Lot 15). A previous version of this document
  didn't mention this function at all, despite it being the concrete implementation of
  ADR-0006's engine selection.
- `load_application(path) → ApplicationService`: builds the full `ApplicationService` (below).

#### `app/application.py` → `ApplicationService`
A composition-root convenience class wrapping the wiring `api/`/`cli/` both need (manifest,
registry, engine, capability validation) behind one object, so neither entry point re-derives that
sequence independently. `app/public.py` re-exports the pieces `api/`/`cli/` are meant to import
(`load_application`, `resolve_manifest`, `validate_capabilities`, `create_default_registry`,
`ingest_path`/`ingest_directory`, `TenantContext`/`TokenVerifier`, and the core error types) as a
single, deliberately narrow public surface — not present in a previous version of this document.

#### `app/lifecycle.py`
`startup(container)` + `shutdown(container)`: process startup/shutdown hooks. Currently just
logging — a placeholder for managing DB connections, cleanup, etc. Distinct from the *document*
lifecycle ledger (`ingestion/lifecycle/`, `contracts/lifecycle.py`) — same word, different concern:
this file is about the *process's* lifecycle, not a document's re-ingestion identity.

---

### `cli/` — Command-line interface

**`cli/__init__.py`** → `app` (Typer instance, `mrag` entry point)

Commands:
- `mrag ingest <path> --manifest <yaml> [--tenant-id <id>]`: loads the pipeline, ingests the
  documents, prints the number indexed. `--tenant-id` applies to every chunk from this call;
  required against a manifest with `governance.tenant_policy` wired — checked explicitly before
  parsing/indexing anything (including an empty or all-unsupported-files input), not only via the
  per-chunk policy check downstream.
- `mrag ask "<question>" --manifest <yaml> [--tenant-id <id>]`: loads the pipeline, asks the
  question, prints the answer + citations with scores. Same fail-closed identity requirement, on
  the query side.
- `mrag validate <manifest>`: schema + capability checks only, no wiring/instantiation (Lot 9).
- `mrag manifest-schema`: prints `PipelineManifest`'s JSON Schema.
- `mrag reconcile --manifest <yaml> [--mode check|repair]` (ADR-0011): wraps
  `orchestration.reconciliation.IndexReconciler` — `check` reports ledger-vs-store divergence,
  `repair` additionally deletes orphaned ids. Uses `--manifest` like the commands above (real
  request-path components, not a direct DB connection).
- `mrag db migrate|rollback|status --dsn <dsn> [--target <version>] [--steps <n>]` (ADR-0011):
  wraps `adapters.postgres.migrations.MigrationRunner`. `--dsn`, never `--manifest` — needs a
  schema-owning (`CREATE`-capable) role the application's own runtime role should never hold
  (`docs/guides/postgres-permissions.md`).
- `mrag audit purge|count-expired --dsn <dsn>` (ADR-0011): wraps
  `PostgresAuditSink.purge_expired()`/`count_expired()`. `--dsn`, never `--manifest` — `purge`
  needs the separate `retention_role` (`DELETE` on `audit_events`), which the manifest's own
  `audit_sink:` DSN should never grant.
- `mrag version`: prints `__version__`.

`reconcile`, `db`, and `audit` route through `app/postgres_admin.py`/`app/application.py`'s
public facades (`app/public.py`), never importing `adapters/` directly — `scripts/
check_layering.py --strict` enforces that `cli/`/`api/` may only import `app/` or their own
interface package.

The CLI has no `TokenVerifier` concept — `--tenant-id` is an operator-supplied flag trusted at
face value, the same local-trust model as any other CLI argument, not a verified identity (see
[threat-model.md](threat-model.md)).

---

### `api/` — REST API

**`api/__init__.py`** → `create_app(manifest_path, token_verifier=None, rate_limit_per_minute=…,
max_body_bytes=…) → FastAPI`

Factory pattern. Routes:
- `GET /health` → liveness; never requires auth.
- `GET /ready` → readiness (Lot 6, superseding the Lot 16a stub) — probes every wired component
  implementing `contracts.health.HealthCheckable` (Qdrant, PostgreSQL, and the configured LLM
  generator via a real, cached, non-generative authenticated call) and returns
  `healthy`/`degraded` (200) or `unready` (503); see [docs/api/rest.md](../api/rest.md#get-ready)
  for the full status/criticality contract.
- `POST /answer` (body: `QuestionRequest{question, k}`) → `AnswerResponse{text, citations,
  trace_id}`.
- `GET /retrieve?q=<question>&k=<n>` → `[{chunk_id, score, content}]`.

`create_app()` refuses to start if a manifest wires `governance.tenant_policy` but no
`token_verifier` was passed — see [threat-model.md](threat-model.md)'s Boundary 1. Three
middleware classes (`api/middleware.py`) wrap every request: `RateLimitMiddleware` (Lot 16a, 429 +
`Retry-After` header, a flat process-wide ceiling), `MaxBodySizeMiddleware` (Lot 16a, 413), and
`ConcurrencyLimitMiddleware` (Lot 6, 503 when more than `max_concurrent_requests` requests are
in flight at once — a different axis from the rate limit: simultaneous load, not requests over
time). `/health` and `/ready` are exempt from all three. Internal
exceptions are mapped through `api/errors.py`'s `to_http_exception()` — a typed exception→HTTP
mapping, not the raw `str(exc)` a previous version of this document (accurately, at the time)
described as leaking into the response body. `/answer` and `/retrieve` both accept an optional
bearer token, verified via the configured `token_verifier` into a `TenantContext` that flows
through as `tenant_id`/`user_id`/`roles`.

---

## `tests/` — Test suite

```
tests/
├── __init__.py
├── unit/               ← Fast, no external services required — mirrors src/modular_rag/ closely,
│                          plus tests/unit/scripts/ (testing scripts/check_layering.py,
│                          check_lock_sync.py, and check_dockerfile_permissions.py themselves) and
│                          tests/unit/e2e/ (testing e2e-fixture helpers that don't themselves need
│                          live services, placed here so `check.sh full`'s unit-scope actually
│                          runs them — files directly under tests/e2e/ are only selected by the
│                          `-m e2e` marker filter)
├── contract/            ← Verify that an implementation satisfies its Protocol
├── integration/          ← Require Qdrant on localhost:6333 (real content today, not empty — see
│                            below)
├── e2e/                    ← Full pipeline, `-m e2e`; some scenarios need an LLM key, the secure-
│                              deterministic scenario deliberately doesn't (see below)
├── benchmark/                ← Still empty — V3 scope
└── fixtures/                   ← Still effectively empty at the top level; data-classification
                                   fixtures live under tests/unit/fixtures/ instead
```

**Contract tests** (`isinstance(obj, Protocol)` conformance, parameterized over every
implementation of a given Protocol) now cover far more Protocols than the original three-file set:
chunker, retrieval, security, eval, parser, reranker, audit, review, lifecycle, telemetry, and
engine conformance each have their own `test_*_conformance.py` — including
`tests/contract/test_engine_conformance.py`, which exercises both `NativeEngineAdapter` and
`LangGraphEngineAdapter` against the same `DocumentEngine` contract, and
`tests/contract/fakes/document_engine.py`, a minimal fake engine used to test the port itself in
isolation. `VectorRetriever` and `HybridRetriever` remain excluded from contract tests that would
require a live Qdrant — those are covered under `tests/integration/` instead.

**`tests/integration/`** is not empty: `test_vector_retriever.py`, `test_qdrant_store.py`,
`test_postgres_audit_sink.py`, `test_postgres_lifecycle_ledger.py`, and (ADR-0011)
`test_postgres_migrations.py` all require real backing services (Qdrant, and for the
Postgres-backed ones, PostgreSQL) — none run in CI today (no Postgres/Qdrant service container is
configured in `.github/workflows/ci.yml`), written and reviewed but not executed in this
sandboxed environment either.

**`tests/e2e/`** is not empty either: `test_simple_qa_pipeline.py` (needs a real LLM key) and
`test_secure_preset_e2e.py` (13 tests over the secure, tenant-isolated preset — needs Qdrant and
PostgreSQL, but deliberately no LLM key, using the deterministic embedder/generator pair) plus
their shared fixture/replay helper modules.

---

## `docs/` — Documentation

```
docs/
├── adr/                          ← 14 ADRs (0001–0014) plus an _index.md
├── api/
│   └── rest.md                   ← REST reference (endpoints, schemas, error codes)
├── architecture/
│   ├── overview.md                ← V1→V5 technical spec, six planes, contracts, wiring, errors
│   ├── data-model.md               ← All Pydantic models, fields, invariants, lifecycle
│   ├── module-model.md              ← Exhaustive module tree, dependency rules, adapter pattern
│   ├── runtime-flow.md               ← Mermaid sequences: V1 query + ingestion, engine delegation
│   ├── security.md                    ← Attack surfaces, guard chain, regex patterns, PII types
│   ├── threat-model.md                 ← Assets, trust boundaries, actors, STRIDE pass
│   ├── data-classification-policy.md    ← Sensitivity levels, PII/tenant schema (Lot 11a)
│   ├── document-engine-contract.md       ← The DocumentEngine port in depth
│   ├── capability-matrix.md               ← Per-engine capability comparison
│   ├── structure.md                        ← This file
│   ├── roadmap-mermaid.md                   ← Timeline/dependency/wiring diagrams
│   └── _index.md
├── guides/                          ← ~35 files: getting-started, installation, deployment,
│                                       observability, plugin-development, validation, backup-
│                                       restore, audit-traceability, troubleshooting, and the
│                                       Claude Code / model-routing / AI-workflow guide set
├── observability/                   ← Reference dashboard, Prometheus alerts, SLOs and runbooks
├── refactoring/                     ← Per-lot execution records (Lot 2, 17, and others)
├── refactoring-plan.md               ← The full 18-lot programme, current-state gaps, change log
└── archive/                          ← Superseded/low-utility documents, kept for the record
    ├── 0004-strategic-features-v1-v5.md    ← Full text of ADR-0004 (a stub remains in docs/adr/)
    ├── feature-integration-plan.md          ← Pre-ADR-0005 commercial/staffing plan
    ├── working-with-agents.md                ← Pre-ADR-0005 native multi-agent design guide
    └── 2026-05-20-initial-review.md           ← Initial review (strengths, weaknesses, decisions)
```

---

## `manifests/` — YAML configurations

> **Runnable vs. Blueprint (see `manifests/README.md`):** since
> [ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md) (Étape 7),
> `presets/` contains only manifests that load, validate, and wire cleanly — non-executable
> sketches live under `blueprints/` instead.

```
manifests/
├── presets/
│   ├── local-hybrid-rag.yaml         ← V1 local dev (HuggingFace + Qdrant localhost + GPT-4o-mini) — Runnable
│   ├── secure-enterprise-rag.yaml    ← V2 native (tenant isolation + policy engine + Postgres audit) — Runnable
│   └── langgraph-rag.yaml            ← V2 delegated (engine.adapter: langgraph) — Runnable
├── blueprints/
│   ├── graph-memory-rag.yaml         ← GraphRAG sketch — delegated traversal not provided by selected engine
│   └── multimodal-rag.yaml           ← Multimodal sketch — VLM execution delegated, parsing/enrichment status open
├── dev/                              ← Dev environment overrides (V4, currently empty)
├── staging/                          ← Staging overrides (V4, currently empty)
└── production/                       ← Production overrides (V4, currently empty)
```

| Manifest | Version | Status | LLM | Embedder | Governance | Notable |
|---|---|---|---|---|---|---|
| `local-hybrid-rag` | V1 | Runnable | gpt-4o-mini | bge-small-en-v1.5 | none | Development, Qdrant localhost |
| `secure-enterprise-rag` | V2 | Runnable | gpt-4o | bge-base-en-v1.5 | tenant isolation + redaction + inline policy engine + Postgres audit | Requires QDRANT_URL/QDRANT_API_KEY/AUDIT_DATABASE_URL; regression gates run offline |
| `langgraph-rag` | V2 | Runnable | gpt-4o | bge-base-en-v1.5 | none | `engine.adapter: langgraph` — real `LangGraphEngineAdapter`, not native agents |
| `graph-memory-rag` | — | Blueprint | gpt-4o | bge-base-en-v1.5 | — | GraphRAG traversal delegated, unavailable in selected engine today |
| `multimodal-rag` | — | Blueprint | claude-opus-4-7 | multimodal (unregistered) | — | VLM execution delegated; parsing/enrichment status open |

`tests/e2e/manifests/secure-deterministic-rag.yaml` is a fourth, test-only manifest: a
deterministic twin of `secure-enterprise-rag.yaml` swapping in `DeterministicEmbedder`/
`DeterministicGenerator` so the secure-preset e2e scenario needs no LLM key.

---

## `examples/` — Example applications

```
examples/
├── simple_qa/                    ← Complete, runnable example (V1)
│   ├── main.py                   ← argparse CLI: ingest + ask
│   ├── README.md                 ← Prerequisites, walkthrough, demonstrated features
│   └── docs/                     ← Sample documents used as the ingested corpus
├── agentic_rag/                  ← Placeholder — would demonstrate engine delegation (LangGraph), not native agents
├── graph_memory/                 ← Placeholder — GraphRAG delegated, no native example possible today
├── hybrid_search/                ← Populated V1 variant, currently not runnable as documented
└── secure_rag/                   ← Secured-V1 placeholder
```

`hybrid_search/` contains code and a README, so it is not an empty placeholder. Its entry point is
nevertheless incompatible with the current `HybridRetriever` (`_bm25` was renamed to `_lexical`),
and its separate `ingest` then `search` commands cannot preserve the process-local BM25 index.
Treat it as a code sample until the implementation is repaired; `simple_qa/first_query.py` is the
current runnable hybrid demonstration.

**`examples/simple_qa/main.py`** — the reference script:

```python
# Ingestion
pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
chunks = ingest_directory("./docs", AdaptiveChunker())
pipeline.ingest_chunks(chunks)

# Question
answer = pipeline.answer("What is RAG?")
print(answer.text)
for c in answer.citations:
    print(f"  [{c.source}] score={c.score:.3f} — {c.passage[:80]}…")
```

---

## Architectural principles recap

| Rule | Why |
|---|---|
| **Contracts first** | Before any concrete implementation, the Protocol exists and is tested |
| **No cross-domain imports** | A retriever cannot import from `generation/` — test isolation without an LLM |
| **Manifests as source of truth** | Runtime pipeline components are selected in YAML; parser dispatch, engine adapters and API identity follow explicit composition paths |
| **Tests mirror src/** | `tests/unit/ingestion/chunkers/test_fixed.py` for `src/modular_rag/ingestion/chunkers/fixed.py` |
| **ADR before structural changes** | Any new layer or contract requires an ADR under `docs/adr/` |
| **Observability is mandatory for new execution steps** | Choose Trace/Telemetry, Tracer and/or Meter at an orchestration boundary; current coverage and gauge limitations are tracked in `docs/guides/observability.md` |
| **Safety ≠ Security** | Safety (injection, PII) lives in filters/redaction; security includes tenant isolation and policy enforcement. RBAC is not implemented |
| **Delegate, don't reimplement** | Generic multi-agent orchestration, GraphRAG traversal, fine-tuning execution, and multimodal VLM execution are delegated to a selected external engine (ADR-0005) — this codebase owns governance/audit/eval/portability around that engine, not the engine's own mechanics |
