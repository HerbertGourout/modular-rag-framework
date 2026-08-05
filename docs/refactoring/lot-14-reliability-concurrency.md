# Lot 14 — Reliability, Concurrency, Resource Lifecycle

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** none directly — touches components introduced across many prior lots.

## What was done

Per `docs/refactoring-plan.md`: "Define sync/async execution, timeouts, retry eligibility,
cancellation, circuit breaking, backpressure, overload, and graceful shutdown. Own and close
clients/resources. Make lazy initialization and mutable indexes concurrency-safe or explicitly
single-worker. Add fault, concurrency, soak, and bounded-load evidence."

### Timeouts

`OpenAIGenerator`, `AnthropicGenerator`, `OpenAIEmbedder`, and `QdrantStore` all gained a
`timeout: float = 30.0` constructor parameter, threaded into the real SDK client constructor
(`openai.OpenAI(..., timeout=...)`, `anthropic.Anthropic(..., timeout=...)`,
`qdrant_client.QdrantClient(..., timeout=...)`). Tested against the **real, installed SDKs** (all
three are present in this environment's `.venv` from the Lot 3 `[v1]` install) — client
construction does no network I/O, so this proves the kwarg is genuinely accepted and reaches the
library, not just stored on this package's own wrapper. `QdrantClient`'s own `timeout` is
int-seconds only (unlike the other two, which take float); truncated (not rounded) so a
sub-second request never silently becomes a *longer* timeout than asked for.

### Retry eligibility and circuit breaking

**`core/resilience.py`** (new): `retry_with_backoff()` (exponential backoff, injectable `sleep`
for deterministic tests) and `CircuitBreaker` (closed/open/half-open, injectable `clock`).
Deliberately **not wired into any adapter automatically** — retry/circuit-breaking policy (how
many attempts is right for an LLM call vs. a vector-store call) is a per-adapter decision left to
whoever configures a pipeline, not something this lot imposes globally. `DEFAULT_RETRYABLE_ERRORS`
is `(ConnectionError, TimeoutError)` only — retry eligibility explicitly excludes this framework's
own `SecurityError`/`PolicyViolationError`/`ConfigurationError`: retrying a deliberate denial would
be actively wrong, not just wasteful (regression test:
`test_retry_never_retries_a_security_error`). `CircuitBreaker`'s half-open trial failing re-opens
the circuit immediately rather than requiring `failure_threshold` failures to accumulate again —
the correct semantics for "give the dependency one chance, not five."

### Graceful shutdown

**`Container.close()`** (new): calls `.close()` on every registered component that has one
(duck-typed — most components, e.g. chunkers, correctly have none). One component failing to
close is logged and does not stop the rest from closing — a partial shutdown leaking one
connection is better than one that stops at the first failure and leaks everything after it.
`OpenAIGenerator.close()`, `AnthropicGenerator.close()`, `OpenAIEmbedder.close()`, and
`QdrantStore.close()` all release their lazily-opened client, if one was ever opened (a no-op
otherwise — closing a resource that was never acquired is not an error).

### Concurrency-safety for mutable in-memory state

Four in-memory reference implementations introduced or touched across this session gained a
`threading.Lock` around their mutating/reading methods:

- **`InMemoryAuditSink`** (Lot 10) — `list.append()` happens to be atomic under CPython's GIL, but
  that's an implementation detail this reference implementation shouldn't rely on silently.
- **`InMemoryLifecycleLedger`** (Lot 12a) — `record_ingested()` is a genuine read-then-write
  (read the existing version, write version+1): a real race under concurrent calls for the *same*
  `document_key`, not just a defensive precaution. Proven with a real-threads test: 50 concurrent
  `record_ingested()` calls on one key produce exactly versions 1 through 50, no duplicates, no
  gaps (`test_concurrent_record_ingested_on_the_same_key_never_loses_an_update`).
- **`HumanReviewGate`** (Lot 11c) — `resolve()` is the same read-then-write shape.
- **`BM25Retriever`** (touched in Lots 12a/12b) — `_chunks` and `_bm25` are two separate attributes
  updated together by `_rebuild()`; a concurrent `retrieve()` between those two assignments could
  otherwise see a new corpus paired with a stale model. `retrieve()` snapshots both under the lock
  before scoring (so scoring itself happens lock-free), and `index()` now reassigns `_chunks`
  (`self._chunks + list(chunks)`) rather than mutating in place (`.extend()`), so a snapshot taken
  by a concurrent `retrieve()` is never mutated out from under it after being handed out. Proven
  with real threads hammering `index()` and `retrieve()` concurrently
  (`test_concurrent_retrieve_during_indexing_never_raises`).

`PostgresLifecycleLedger`/`PostgresAuditSink` are not touched here — PostgreSQL owns its own
concurrency control (transactions, row locking); adding an in-process Python lock around a
database client would be redundant at best and could mask real contention at worst.

## Sync/async execution semantics (documented, not retrofit)

Per the plan's phrase "define sync/async execution" — this lot documents the current state rather
than rewriting every `a*` method, which would be a much larger undertaking than this lot's other
four deliverables combined:

- **`HuggingFaceEmbedder.aembed()`** is the one adapter that does this correctly today: it runs
  the blocking `embed()` call in a thread executor (`loop.run_in_executor`), so it genuinely
  doesn't block the event loop.
- **Every other `a*` method in this codebase** (`OpenAIGenerator.agenerate()`,
  `AnthropicGenerator.agenerate()`, `BM25Retriever.aretrieve()`, `VectorRetriever.aretrieve()`,
  `HybridRetriever.aretrieve()`, `NativeEngineAdapter.arun()`) is a synchronous call wrapped in a
  coroutine — it does not yield control to the event loop while the underlying work runs.
  `OpenAIEmbedder.aembed()` is the partial exception: it does use the SDK's real
  `AsyncOpenAI` client (genuine non-blocking I/O for the network call itself), but `embed()`'s
  batching loop around it is still fully synchronous inside the coroutine.
- **Recommendation, not enforced**: a caller running `RAGEngine.answer()` (fully synchronous) from
  an async context (e.g. a FastAPI route) should use a thread executor
  (`starlette.concurrency.run_in_threadpool` or equivalent) rather than calling it directly inside
  an `async def` route handler — `api/__init__.py`'s current `/answer` handler is itself a
  synchronous `def`, which FastAPI already runs in a thread pool automatically, so this is
  correctly handled today for that one call site, but is not a general guarantee for other
  callers.

## Cancellation (still open, honestly recorded)

`contracts/engine.py`'s `CancellationToken` (Lot 7) exists in the port, but `NativeEngineAdapter`
declares an empty capability set and explicitly ignores it (Lot 8's own documented design — "not
the same thing as this port's `GovernanceHook`"). This lot does not change that: wiring cooperative
cancellation checks into `RAGEngine._run_steps()` between pipeline stages would be a genuine new
capability, not a reliability fix to existing behavior, and is left for whichever lot first needs
it in practice (likely Lot 15's LangGraph adapter, which may have native cancellation support to
expose through the same port).

## Backpressure, overload, soak and bounded-load evidence (infrastructure-blocked, documented)

Per this session's established pattern for infrastructure this sandboxed environment doesn't have:
genuine backpressure/overload testing needs a running pipeline under real concurrent load (a load
generator against a live API, not a unit test), and soak testing needs sustained real time, not a
fast-running test suite. Not fabricated here. What this lot *does* provide as evidence:

- **Concurrency evidence**: the four lock-protected components' real-threads tests above are
  genuine concurrency evidence — proof that concurrent access does not corrupt state — even though
  they're not soak tests (they run for milliseconds, not hours).
- **Fault evidence**: `CircuitBreaker`'s tests (`test_circuit_breaker_opens_after_threshold_failures`,
  `test_circuit_breaker_half_open_failure_reopens_immediately`) are fault-injection evidence for
  the primitive itself.
- **Bounded-load / overload testing** genuinely requires a deployed instance and a load-generation
  tool (e.g. `locust`, `k6`) run against it — flagged for Lot 16c's deployment runbooks, alongside
  the PostgreSQL/Qdrant backup procedures Lot 12c similarly deferred there.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 508 tests total (426 unit + 82 contract, up from 471 at Lot 13).
- mypy baseline unchanged at 34.
- Timeout tests run against the real installed `openai`/`anthropic`/`qdrant-client` SDKs, not
  mocks — genuine compatibility proof, not just "this package's own code runs."
- Concurrency tests use real OS threads (`concurrent.futures.ThreadPoolExecutor`), not simulated
  interleaving.

## Lot 14 acceptance (per its own description in `docs/refactoring-plan.md`)

Timeouts, retry eligibility, circuit breaking, and graceful shutdown are delivered as real,
tested, callable mechanisms. Concurrency-safety is delivered for the mutable in-memory reference
implementations this session introduced. Sync/async execution semantics and cancellation status
are documented honestly rather than silently left implicit or overclaimed as fixed. Backpressure/
overload/soak evidence requires live infrastructure this environment doesn't have and is deferred
to Lot 16c, consistent with this session's established pattern for infra-blocked work.

## Next

Lot 15 (the selected external adapter — LangGraph, per ADR-0006): must pass the same semantic
engine, governance, audit, migration, quality, cancellation, and failure tests as the native
adapter (Lot 8). This is where `EngineCapability.CANCELLATION` may first get a real implementation
if LangGraph exposes native cancellation this port can delegate to.
