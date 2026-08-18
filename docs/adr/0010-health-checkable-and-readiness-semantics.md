# ADR-0010 — `HealthCheckable` port and readiness semantics

**Status:** Accepted
**Date:** 2026-08-17

## Context

The readiness-and-resilience work wiring `GET /ready` to real dependency probes (`QdrantStore`,
`QdrantSparseStore`, `PostgresLifecycleLedger`, `PostgresAuditSink`, and — since Codex review
HIGH-001, second pass — `OpenAIGenerator`/`AnthropicGenerator`) introduced a new public port
(`contracts/health.py`'s `HealthCheckable`), two new models (`core/models/health.py`'s
`DependencyHealth`/`ReadinessReport`), a duck-typed discovery/aggregation mechanism
(`orchestration/container.py`'s `Container.check_readiness()`), and a role-based criticality
notion (`_CRITICAL_ROLES`). None of this was covered by an ADR before landing — a real gap:
`CLAUDE.md` §07 requires one for "any new top-level module, new layer boundary, or contract
modification," and this qualifies (a genuinely new Protocol, reachable by any future component,
with no recorded decision on its compatibility/evolution rules).

This ADR documents the design as built and already shipped — it does not propose new scope. Per
`docs/adr/_index.md`'s own process note, an ADR can ratify an existing decision rather than
gate future work behind one.

## Decision

### 1. Port boundary

`contracts/health.py`:

```python
@runtime_checkable
class HealthCheckable(Protocol):
    def check_health(self) -> list[DependencyHealth]: ...
```

Optional and duck-typed, not a required member of any other Protocol (`Indexer`, `Retriever`,
`Generator`, `AuditSink`, `LifecycleLedger` do not extend it). `Container.check_readiness()`
discovers implementers via `getattr(component, "check_health", None)`, the same style already
established by `Container.close()` — `orchestration/` may only import `core/` + `contracts/` +
its own package, never a concrete adapter, so it cannot `isinstance()`-check against one. A
component simply omitting `check_health()` (in-memory `BM25Retriever`, a no-op audit sink) is
not an error — it contributes nothing to the report, not a forced `unhealthy`.

Returns a **list**, not a single result, so a component wrapping more than one external
dependency can report zero or more entries — `HybridRetriever.check_health()` delegates to
whichever lexical backend is wired (empty for in-memory BM25, one entry for
`PersistentSparseRetriever`).

### 2. Three-state semantics

`core/enums.py`'s `ReadinessState`: `HEALTHY`, `DEGRADED`, `UNREADY`. `GET /ready` maps
`UNREADY` → HTTP 503, `HEALTHY`/`DEGRADED` → 200. An orchestrator should stop routing traffic
only on `UNREADY`; `DEGRADED` means "still able to serve, at reduced capability or resilience,"
not "broken."

### 3. Critical capabilities

A role is critical — its failure escalates the whole pipeline to `UNREADY` — under exactly one
test: **would this role's failure produce an unhandled exception on the query-serving path**
(`RAGEngine.answer()`/`retrieve()`), given the engine's actual, current exception handling. Not
"is this component used somewhere," not "does it feel important" — verified against real code
each time (`RAGEngine._audit()`'s missing try/except around `audit_sink.record()`;
`RAGEngine._run_steps()`'s missing try/except around `generator.generate()`). Currently:
`audit_sink` (when wired) and `generator` (always required).

`indexer` and `retriever` are deliberately **not** individually critical —
`HybridRetriever._safe_retrieve()` already catches a failure on either leg and degrades
gracefully — but `Container.check_readiness()` escalates the specific combination of **both**
reporting every entry unhealthy to `UNREADY`, since that means no retrieval leg is confirmed
usable at all (the exact topology `secure-enterprise-rag.yaml` creates: dense and sparse legs
share one Qdrant server). This is a capability-level rule layered on top of the per-role
exception-based one, not a replacement for it — see `orchestration/container.py`'s own extensive
comment for the full reasoning and the specific preset evidence.

`lifecycle_ledger` and (individually) `indexer`/`retriever` failures are ingest-path or
gracefully-degraded concerns respectively, reported as `DEGRADED`, not `UNREADY` — a serving
pod's traffic eligibility is what `/ready` gates, not an offline ingest job's success.

**Residual, explicitly not solved by this ADR**: a manifest wiring a *bare* `VectorRetriever` or
`PersistentSparseRetriever` as `retriever` (no `HybridRetriever` fallback — not used by any
shipped preset today) has no graceful degradation, so `DEGRADED` would be optimistic for that
specific configuration. `Container` has no visibility into a retriever's internal composition
beyond the registered component itself, so this cannot be detected generically without a richer
capability-declaration mechanism than exists today.

### 4. Probe budget and side effects

- **No retries inside `check_health()`.** A single fast attempt only — k8s's own probe interval
  is the retry mechanism. Retrying inside the probe would make an already-slow dependency block
  `/ready` for a multiple of its real timeout.
- **Never write.** A cold, never-connected Qdrant store's `check_health()` probes with a bare,
  throwaway client rather than the real `_get_client()`/`_ensure_collection()` path specifically
  to avoid `create_collection()` running as a probe side effect. Collection/vector-size/sparse-
  modifier validation added in this pass (Codex review HIGH-001, second pass) is read-only
  (`get_collections()`/`get_collection()`), never a write. The throwaway cold-path client itself is
  closed in a `finally` on every exit path (Codex review MEDIUM-002, fourth pass) — never left
  unclosed for the garbage collector to eventually reclaim, and never the warm, shared
  `self._client`, which `check_health()` never closes.
- **The vector-size comparison is resolved, not skipped, when uncertain — but never by triggering a
  real model load from inside a probe.** A cold probe against a manifest that leaves `vector_size`
  unset (both `secure-enterprise-rag.yaml` and `langgraph-rag.yaml` do, deriving 768 from their BGE
  embedder) compares against a not-yet-derived constructor default (384) if taken naively — an
  early (third-pass) fix avoided that false positive by *skipping* the comparison whenever cold and
  non-explicit, which reintroduced the original gap: a genuinely wrong collection (an existing
  384-dim collection against a bound 768-dim embedder) reported healthy again, unconditionally,
  until real traffic hit `_ensure_collection()` (Codex review HIGH-003, fourth pass — reproduced
  live). Fixed (fourth pass) by resolving the expected size from the bound embedder's `.dimensions`
  directly when not explicit, instead of skipping. That fix carried its own residual gap (Codex
  review HIGH-002, fifth pass — reproduced live): `.dimensions` is not uniformly cheap —
  `HuggingFaceEmbedder.dimensions` falls back to `_get_model()`, a real `sentence_transformers`
  download/load with no timeout and no lock against concurrent redundant loads, for any model name
  outside its static `_DIMENSIONS` table. A probe against a bound embedder using an unrecognized
  model name could therefore hang pod startup indefinitely on a slow or unreachable model registry,
  even with Qdrant itself fully healthy — contradicting the "never trigger a costly first-use
  side effect from a probe" rule this same bullet exists to uphold. Fixed by adding a new,
  optional, duck-typed `known_dimensions() -> int | None` method to all three `Embedder`
  implementations (`HuggingFaceEmbedder`, `OpenAIEmbedder`, `DeterministicEmbedder`) — a
  cheap-only variant that returns the dimension when free to compute (a static-table/dict lookup)
  and `None` otherwise, never falling back to a real model load.
  `QdrantStore._probe_collection()` now resolves the expected size via
  `getattr(embedder, "known_dimensions", None)`, falling back to the manifest's configured
  `vector_size` when that returns `None` (never touching `.dimensions` from a probe). Deliberately
  not a new `Embedder` Protocol member — `CLAUDE.md` §07 requires an ADR for a contract
  modification, and this stays a narrower, duck-typed extension in the same style
  `HealthCheckable` itself established (§1).
- **Bounded, dependency-scoped timeouts**, distinct from the timeout governing real traffic:
  `_HEALTH_CHECK_TIMEOUT` (Qdrant/Postgres connect budget), `_HEALTH_QUERY_TIMEOUT_MS` (a real
  PostgreSQL `statement_timeout` — Codex review MED-002, second pass — since `connect_timeout`
  alone does not bound a query stuck on an already-established connection). Postgres's design was
  revised twice after the original warm/cold split shipped: the second version (third/fourth pass)
  reused the shared, cached connection on a "warm" path — bounding `self._lock` acquisition with
  `_HEALTH_LOCK_ACQUIRE_TIMEOUT` (reporting `"busy"` on timeout), then issuing `SHOW
  statement_timeout` / `SET statement_timeout = ...` / the probe query / a restoring `SET` back to
  the exact prior value, all under that lock. Codex review HIGH-001 (fifth pass, reproduced live)
  found this still under-bounded in three compounding ways: the `SHOW`/first `SET` themselves ran
  with no query-level deadline active yet, so a connection whose transport had gone silent after
  the original TCP handshake (network partition, dropped NAT mapping) could hang the probe
  indefinitely before `statement_timeout` took effect; even once active, a server-side
  `statement_timeout` only fires if the server's backend process is alive to enforce it, so it
  cannot detect a transport gone silent client-side; and the whole warm path mutated
  `self._lock`-guarded shared state from what is supposed to be a side-effect-free probe.
  `PostgresLifecycleLedger`/`PostgresAuditSink.check_health()` were redesigned to always open a
  fresh, dedicated, short-lived probe connection — cold or warm makes no difference, so there is
  only one code path, and it never touches `self._conn` or `self._lock` at all. `statement_timeout`
  is baked into the connection itself via `options=f"-c statement_timeout={_HEALTH_QUERY_TIMEOUT_MS}"`
  passed to `psycopg.connect()`, active from the very first query rather than a separate SHOW/SET
  step — closing the unprotected window the prior design had. TCP keepalive parameters
  (`_HEALTH_KEEPALIVE_IDLE`/`_INTERVAL`/`_COUNT`, aggressive since this connection exists for one
  query and is torn down immediately) bound how long the OS takes to notice a transport gone silent
  after the handshake, independent of anything the server enforces — the piece a server-side
  timeout alone could never cover. `_HEALTH_LOCK_ACQUIRE_TIMEOUT` and the `"busy"` verdict were
  removed entirely for Postgres: with nothing shared ever touched, a live request holding
  `self._lock` for a real query has no bearing on readiness anymore. This also resolved Codex
  review MEDIUM-001 (fourth pass — a failed `statement_timeout` restore previously reported
  `healthy=True` while leaving the shared connection's session state unknown) as a side effect:
  there is no longer a shared connection for a probe to leave in a corrupted state at all.
- **A real, authenticated, non-generative call against the specific configured model, cached, and
  bounded.** `OpenAIGenerator`/`AnthropicGenerator.check_health()` call
  `client.with_options(timeout=_HEALTH_CHECK_TIMEOUT, max_retries=0).models.retrieve(self.model)`
  — a per-call view of the client, not the shared one, so the probe never inherits `self.timeout`
  (30s, sized for a real generation call) or the SDK's own default `max_retries=2` (both verified
  live on the installed versions — a network partition could otherwise hold a probe for minutes
  across retries, contradicting the "single, short, bounded attempt" rule directly below; Codex
  review HIGH-002, fourth pass). `self._health_lock` is itself now acquired with a bound
  (`_HEALTH_LOCK_ACQUIRE_TIMEOUT`) rather than indefinitely, reporting `"busy"` on timeout, so a
  probe stuck despite the above can't also block every other concurrent `/ready` call behind the
  same lock. `models.retrieve(self.model)` — not `models.list()`, whose result an earlier version
  discarded entirely (Codex review HIGH-004, fourth pass: a valid key for *any* model reported
  healthy even if `self.model` itself was misspelled, retired, or inaccessible to this account) —
  validates the credential against the *specific* configured model, catching the same
  `AuthenticationError`/`NotFoundError` a real `generate()` call would hit. Cached for 30s per
  generator instance (`_HEALTH_CHECK_CACHE_SECONDS`, guarded by the same lock, which also
  serializes concurrent cache-miss refreshes into one real call) — the Lot 6 "no costly LLM call
  per probe" criterion is honored by bounding *frequency*, not by avoiding the call altogether:
  `/ready` is unauthenticated and rate-limit-exempt, so without a cache a burst of probes could
  trip the provider's own rate limit, making `/ready` flap for reasons unrelated to the actual
  dependency. Residual, still-open limitation: a key valid for retrieving this model's metadata
  but specifically out of quota for the chat/completion endpoint is not distinguishable from a
  fully healthy one — narrower than a full end-to-end check, but a real network+auth+model
  validation, not a local-only credential check.
- **The Anthropic SDK floor is a verified, not assumed, compatible version.** `check_health()`
  needs the SDK's `models` resource; `pyproject.toml` declared `anthropic>=0.28` (Codex review
  HIGH-001, fourth pass) — verified live against the official `anthropic-sdk-python` tags that
  `models` is absent through v0.50.0 and present from v0.51.0 onward, so a floor of `0.28` let
  `pip install -e ".[v1]"` resolve a version where `generate()` works but `/ready` deterministically
  503s with `AttributeError`. Raised to `anthropic>=0.51`.
- **Reads, never writes, `CircuitBreaker` state.** `check_health()` reads `self._circuit.state`
  to fail fast without a network call when already `OPEN`, but never calls `.call()` itself for
  its own round-trip — a periodic probe must not reset real-traffic failure accounting or race a
  live request for the single `HALF_OPEN` trial slot. The one accepted exception: the very first
  connection ever made by a process, if triggered by a health check before any real traffic
  arrives, does go through the circuit once (bootstrap only, never recurring).
- **Global cross-component probe budget: explicitly out of scope.** `Container.check_readiness()`
  probes registered components sequentially; there is no deadline spanning the whole aggregate
  call, and probes are not run concurrently. A pathological deployment with several slow-but-
  individually-bounded dependencies could still make one `/ready` call slower than an
  orchestrator's own probe timeout in aggregate. Flagged by Codex review MED-002 (second pass);
  deferred as a distinct, larger architectural change (concurrent bounded probing, cross-
  component deadline propagation) rather than folded into this pass under "garde le changement
  étroit."

### 5. Error detail handling

`GET /ready` is deliberately exempt from authentication, rate limiting, and the concurrency
limit — an orchestrator's own probe must never be blocked by any of them — which also means it
is reachable by anyone who can route to the process at all. `core/resilience.py`'s
`unhealthy_dependency()` helper is the classification/logging pattern every adapter's
`check_health()` failure branch (and `Container.check_readiness()`'s own defensive catch around a
component's `check_health()` raising) routes through: it classifies the exception to one of a
small set of stable, non-sensitive codes (`timeout`, `unreachable`; plus the literal,
hand-authored `circuit open` and `busy` states, which never touch `str(exc)` at all) with a short
correlation id, and logs the full exception — which can embed hostnames, DSNs, collection names,
or a third-party SDK's own message content — server-side via `structlog`, never in the HTTP
response body. `generation/synthesizers/{openai,anthropic}_gen.py` implement the identical
pattern via a private, file-local `_unhealthy()` rather than importing the shared helper — domain
modules may import only `contracts/` + `core/models/` per `CLAUDE.md` §02, and
`core.resilience` is outside that boundary (Codex review MEDIUM-001, third pass); `adapters/` has
no such restriction and keeps using the shared one.

Hand-authored detail strings for the new HIGH-001 collection-validation checks (missing
collection, named-vector mismatch, vector-size mismatch, missing sparse field, wrong modifier)
are exempt from this classification requirement: they are fully self-authored, drawn only from
internally-known, non-secret values (the configured collection name, an integer dimension), not
from an external exception's unpredictable content, so there is no leak risk to guard against.

### 6. Compatibility rules for a future `HealthCheckable` implementation

- Must return within the caller's expected probe budget — no fixed contract number today
  (per-adapter constants, see §4), but a future implementation should follow the same
  "short, dependency-scoped timeout, no retry" shape.
- Must never mutate state a real request path also depends on (no writes, no `CircuitBreaker`
  side effects beyond the documented bootstrap exception).
- `DependencyHealth.name` is not required to be globally unique — `role` (stamped by
  `Container.check_readiness()`, not the component itself) is what disambiguates two components
  sharing one adapter `name()` (e.g. both Postgres adapters report `"postgres"`).
- `detail` must never contain raw external exception text on a codepath reachable from an
  unauthenticated route — route failures through `core.resilience.unhealthy_dependency()` (from
  `adapters/`) or an equivalent private, file-local implementation of the same pattern (from a
  domain module, which cannot import `core.resilience` — see §5) — never a bare `str(exc)`.
- A domain-module implementation (`generation/`, `retrieval/`, etc.) may import only
  `contracts/` + `core/models/` (`CLAUDE.md` §02) — a health-check helper needing logging or
  exception classification belongs inline in that module, not imported from a wider `core/`
  submodule an adapter could otherwise reach. `scripts/check_layering.py` does not currently
  enforce this narrower domain-module rule (it allows all of `core/`), so this must be checked by
  reading the import, not by relying on the layering script passing.
- A new critical-role designation (extending `_CRITICAL_ROLES` or the capability-escalation
  logic) requires the same evidence discipline used throughout this ADR: read the actual current
  exception-handling code path, don't assume from a component's apparent importance.

## Consequences

- The port, models, and aggregation semantics now have a recorded architectural decision, per
  `CLAUDE.md` §07's requirement — this ADR ratifies the design as already implemented rather
  than gating it behind a future one.
- Future `HealthCheckable` implementations (a plugin, a new adapter) have a documented contract
  to conform to beyond "implements the method" — the compatibility rules in §6.
- The generator gap Codex review HIGH-001/HIGH-003/HIGH-004 (first through fourth pass) flagged is
  now closed for the revoked/malformed/expired/over-quota-key *and* wrong/inaccessible-model
  classes of failure via a real, authenticated, model-specific, rate-limit-and-retry-bounded,
  cached `models.retrieve(self.model)` call — narrowed from "not probed at all," through
  "credential presence only," through "any model is listed" (still ignoring the actual configured
  model and the SDK's own default retries/timeout), to "the specific configured model, bounded to
  a short single attempt, rate-bounded by a cache." The chat/completion-endpoint-specifically-
  unhealthy class (valid for retrieving model metadata, not for completions) and the
  cross-component global-probe-budget class remain explicitly open, tracked here rather than
  silently unaddressed.
- The Qdrant cold-path dimension check went through three revisions in response to review: an
  initial version produced a false positive (comparing against a not-yet-derived default); the
  fix that closed that reintroduced the original false negative (skipping the comparison
  entirely); a third version resolved the real expected size from the bound embedder's
  `.dimensions` instead of choosing between those two failure modes (Codex review
  HIGH-001/HIGH-003, third and fourth pass) — but assumed every embedder's dimension lookup was
  equally cheap, which a real `HuggingFaceEmbedder` bound to an unrecognized model name was not;
  the current version resolves the size via the new duck-typed `known_dimensions()` (§4), cheap by
  construction, falling back to the manifest's configured `vector_size` rather than ever risking a
  real model load from a probe (Codex review HIGH-002, fifth pass).
- The Postgres adapters' `check_health()` went through three revisions in response to review,
  mirroring the Qdrant dimension check's history: an initial version (second pass) branched cold
  (a bare, lock-free connection) vs. warm (the shared, cached connection, with no query-level
  timeout at all beyond `connect_timeout`); a second version (third/fourth pass) bounded the warm
  path's query with a session-level `statement_timeout`, set and restored around it under
  `self._lock`, fixing MED-002 and then HIGH-002/MEDIUM-001 (restoring the exact prior value
  rather than resetting to `0`; flipping to unhealthy on a failed restore instead of swallowing
  it). Codex review HIGH-001 (fifth pass, reproduced live) found that version still hangs
  indefinitely against a transport gone silent after the TCP handshake, since neither the
  pre-`SET` window nor a server-side `statement_timeout` alone can detect that. The current
  version always opens a dedicated, short-lived probe connection with `statement_timeout` baked
  in via `options=` and aggressive TCP keepalives, never touching the shared connection or lock —
  which also resolved MEDIUM-001's underlying concern (a swallowed restore-failure) as a side
  effect, since there is no longer shared session state for a probe to corrupt.
- No code changes are required by this ADR itself — it documents decisions already reflected in
  `contracts/health.py`, `core/models/health.py`, `core/enums.py`'s `ReadinessState`,
  `orchestration/container.py`, the four storage adapters, the three embedder adapters
  (`known_dimensions()`), and the two LLM generators.
