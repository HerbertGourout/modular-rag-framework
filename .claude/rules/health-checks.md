---
paths:
  - "src/modular_rag/contracts/health.py"
  - "src/modular_rag/core/models/health.py"
  - "src/modular_rag/core/resilience.py"
  - "src/modular_rag/orchestration/container.py"
  - "src/modular_rag/adapters/**/*.py"
  - "src/modular_rag/generation/synthesizers/*.py"
  - "src/modular_rag/retrieval/retrievers/*.py"
description: "Invariants every contracts.health.HealthCheckable.check_health() implementation must satisfy — written up front, not discovered reactively per Codex round."
version: "1.0"
lastUpdated: "2026-08-18"
---

# Rules — implementing `check_health()` (`contracts.health.HealthCheckable`)

## Why this file exists

Lot 6 ("readiness and resilience") shipped `HealthCheckable` and its first implementers, then
took **five** Codex review rounds to reach a clean state — one probe-safety defect at a time,
discovered file by file, instead of caught once against a checklist. Every round found a
*variant* of the same handful of invariants (unbounded probe I/O, unbounded probe compute, a
probe mutating state real traffic depends on, a probe leaking raw exception text) in a
*different* adapter than the previous round. See
[ADR-0010](../../docs/adr/0010-health-checkable-and-readiness-semantics.md) §4 for the full,
adapter-by-adapter history.

**This file exists so the next `HealthCheckable` implementation gets these right on the first
pass** — read it *before* writing a new `check_health()`, not after Codex flags something. When
a future round discovers a new invariant this file doesn't yet cover, add it here immediately —
that is the whole point of the file existing.

## The invariants

Every `check_health()` — existing or new — must satisfy all of these. Current implementers:
`QdrantStore`, `QdrantSparseStore`, `PostgresLifecycleLedger`, `PostgresAuditSink`,
`OpenAIGenerator`, `AnthropicGenerator`, `PersistentSparseRetriever`, `HybridRetriever`
(delegates to whichever lexical backend is wired).

### 1. Single attempt, no retry

A probe is one fast, single attempt. k8s's own probe interval is the retry mechanism — retrying
inside `check_health()` multiplies a slow dependency's real latency by the retry count before
`/ready` even responds.

### 2. Read-only — never a write, never a resource creation

A cold, never-connected store must probe without ever triggering the side effects its real
connect path would (e.g. `QdrantStore`'s cold probe uses a bare, throwaway client instead of the
real `_get_client()`/`_ensure_collection()` path, specifically to avoid `create_collection()`
running as a probe side effect).

Any throwaway client/connection opened for the probe must be
closed on every exit path (`finally`, or a context manager) — never left for the garbage
collector, and never the real, shared, long-lived client the rest of the component uses.

### 3. Never trigger unbounded local compute from inside a probe

Not just network calls — a probe must never trigger a real ML model download/load either. If a
value normally requires loading a model to compute (e.g. `HuggingFaceEmbedder.dimensions` falling
back to `_get_model()` for a model name outside its static table), do not call that path from a
probe. Instead, add a cheap-only, optional, duck-typed sibling method that returns `None` when the
answer isn't free to compute, and have the probe fall back to a static/configured value in that
case (`known_dimensions()` is the precedent — see `adapters/embeddings/hf_embedder.py`).

A "cached
afterward" real load is still a real, unbounded first hit — not an acceptable trade for a probe
that an unauthenticated, rate-limit-exempt caller can trigger at will.

### 4. Every network call has its own short, dependency-scoped timeout

Never inherit a timeout or retry policy sized for real traffic. A probe's timeout is a distinct
constant (e.g. `_HEALTH_CHECK_TIMEOUT`), and for SDKs that support a per-call override
(`client.with_options(timeout=..., max_retries=0)` for both the OpenAI and Anthropic Python SDKs),
use it rather than mutating the shared production client.

`connect_timeout` alone only bounds
establishing a connection — a query or call that hangs *after* connecting needs its own bound too
(a real server-side `statement_timeout` for PostgreSQL, a client-side per-call timeout for an SDK
call).

### 5. Never mutate state a real request path depends on

The strongest form of this rule: **give the probe its own dedicated, throwaway resource instead
of touching a shared one at all**, whenever that's possible.

This was the size of the fix that
finally closed HIGH-001 (Lot 6, fifth pass) for the Postgres adapters — earlier versions reused
the shared, cached connection under `self._lock` on a "warm" path, temporarily changing its
session-level `statement_timeout` and restoring it afterward; every version of that approach
carried a residual risk (an unprotected window before the bound took effect, a restore that could
itself fail and leave the connection's state ambiguous). The version that actually closed it
opens a fresh, dedicated connection per probe, with the timeout baked in at connect time via
`options=`, and never touches the shared connection or its lock at all.

Where a dedicated resource
per probe is genuinely impractical, second-best is a *bounded* wait for the shared resource (see
next rule) — never an indefinite one.

### 6. Bound any wait for a contended resource — but prefer not needing one

If a probe must acquire a lock or connection a live request might be holding, bound the wait
(e.g. `_HEALTH_LOCK_ACQUIRE_TIMEOUT`) and report a distinct `"busy"` detail on timeout, rather than
queuing indefinitely. Note that rule 5's dedicated-resource pattern eliminates this concern
entirely where it's applicable — prefer that over a bounded-wait fallback.

### 7. Account for a transport that went silent, not just a slow response

A server-side timeout (`statement_timeout`, an API's own request timeout) requires the *server's*
process to be alive to enforce it — it cannot detect a transport that has gone silent client-side
after a successful handshake (a network partition, a dropped NAT mapping). For raw TCP connections
(PostgreSQL via `psycopg`), pair the server-side timeout with aggressive keepalive parameters
(`keepalives=1, keepalives_idle=..., keepalives_interval=..., keepalives_count=...`) so the OS
itself bounds how long a probe can hang against a peer that stopped responding after the
handshake.

### 8. Read `CircuitBreaker` state, never mutate it from a probe

Check `self._circuit.state` to fail fast without a network call when already `OPEN`. Never call
`.call()` from inside `check_health()` for the probe's own round-trip — a periodic, possibly
anonymous probe must not reset real-traffic failure accounting or race a live request for the
single `HALF_OPEN` trial slot. (The one accepted exception in this codebase: the very first
connection a process ever makes, if triggered by a health check before any real traffic arrives —
bootstrap only, never recurring.)

### 9. Never leak raw exception text to `/ready`

`GET /ready` is deliberately unauthenticated and exempt from rate-limiting and the concurrency
limiter — reachable by anyone who can route to the process. A raw exception (which can embed
hostnames, DSNs, collection names, or a third-party SDK's own message content) must never reach
the HTTP response.

Route every failure through `core.resilience.unhealthy_dependency()` from
`adapters/` (which may import `core/`), or an equivalent private, file-local `_unhealthy()` from a
domain module (`generation/`, `retrieval/`, etc. — which per `CLAUDE.md` §02 may import only
`contracts/` + `core/models/`, not `core.resilience` itself). Both classify to a small set of
stable, non-sensitive codes (`timeout`, `unreachable`, plus hand-authored literals like
`circuit open`/`busy` that never touch `str(exc)`) with a correlation id, logging the full
exception server-side only.

### 10. A genuinely necessary but costly real call: bound frequency, don't skip validation

Some checks can't be made cheap (validating an LLM API key against the *specific* configured
model requires a real, authenticated call). Where that's the case, don't weaken the check to
something cheaper but less meaningful (e.g. don't fall back to "is any model listed" instead of
"is *this* model retrievable") — instead cache the result for a short window (`OpenAIGenerator`/
`AnthropicGenerator` use `_HEALTH_CHECK_CACHE_SECONDS = 30.0`, guarded by a lock that also
collapses concurrent cache-miss refreshes into one real call), so an unauthenticated,
rate-limit-exempt `/ready` can't be used to hammer the provider's own API.

### 11. Prefer a duck-typed extension over a Protocol change for probe-only needs

When a probe needs a capability only some implementers can offer cheaply (rule 3's
`known_dimensions()` is the example), add it as an optional, duck-typed method
(`getattr(obj, "method_name", None)`) rather than a new required member of the domain's real
Protocol (`Embedder`, `Indexer`, etc.). A Protocol change needs its own ADR per `CLAUDE.md` §07;
a narrow, probe-only duck-typed extension does not, and this is the same pattern
`HealthCheckable` itself already uses relative to `Indexer`/`Retriever`/`Generator`.

## Process: how to avoid a repeat of Lot 6's five-round cycle

1. **Before writing a new `check_health()` (or editing an existing one), re-read the 11 rules
   above and check the new code against each one explicitly** — don't wait for Codex to be the
   only line of defense. This is the single highest-leverage change: most of Lot 6's rounds 3–5
   findings were instances of rules 3, 5, and 9 that a five-minute self-review against a checklist
   like this one would have caught before ever running a review.
2. **When a review finds a violation of one of these rules in one implementer, immediately check
   every other current implementer (the list at the top of "The invariants") for the same
   violation, in the same pass** — don't fix only the flagged file and wait for a future round to
   find the same defect in a structural sibling. Lot 6 did this well *within* a pair (both
   Postgres adapters, all three embedders) but not *across* families in the same round (a
   probe-safety defect found in the Qdrant/embedder family in round 5 was fixed there without
   also re-auditing the already-"closed" Postgres family for the same category of gap that same
   round — it happened to also need a fix, caught only because it was already on the pending list,
   not because of a deliberate cross-family sweep).
3. **When a new invariant is discovered that isn't on this list yet, add it here in the same
   change that fixes it.** A finding that only lives in a Codex review transcript or an ADR's
   history section doesn't prevent the next implementer from repeating it; a rule in this file,
   loaded automatically whenever a matching path is touched, does.
4. **For a genuinely new port or capability (not just a new implementer of an existing one),
   write the invariants — even as a short bullet list in the PR description or a draft ADR —
   *before* implementing**, not after. ADR-0010 itself was written retroactively ("ratifies the
   design as already implemented"); had its §4 rules existed as a checklist before the first
   `check_health()` was written, most of rounds 3–5 would not have been separate rounds at all.
