# Lot 6 — External-Engine Fit Spike: Evidence and Selection Matrix

**Status:** Spike complete; recommendation drafted in
[ADR-0006](../../adr/0006-external-engine-selection.md) as `Proposed`, pending Herbert
Gourout's explicit sign-off (sole decision authority, `docs/refactoring/lot-0-baseline.md` §2).
**Since accepted** — ADR-0006 itself now records `Status: Accepted`, dated the same day as this
spike. This record is kept describing the pre-acceptance state, not edited to claim the
recommendation was already final when it was written.
**Date:** 2026-08-04
**Candidates spiked (user's choice):** LangGraph 1.2.10, LlamaIndex Workflows
(`llama-index-core` 0.14.23 / `llama-index-workflows` 2.22.2). Haystack was explicitly not
spiked this round — see "Rejected without a spike" below.

## Representative use case

A governed, single-turn QA request, matching what `RAGEngine._run()` already does today plus
the governance/telemetry/cancellation dimensions the plan requires evaluating:

1. **Route** — a planning/routing step (trivial here; a real one classifies the query).
2. **Retrieve** — call a retrieval "tool" (faked — the point is orchestration, not retrieval
   quality; ingestion/retrieval stay native per ADR-0005 regardless of which engine is picked).
3. **Governance interception** — a guard step that can short-circuit before generation.
4. **Generate** — produce a cited answer.

Both spikes implement *exactly* this pipeline with matching fakes
(`FakeRetriever`/`FakeGuard`/`FakeGenerator`), so the comparison is apples-to-apples. Neither
spike touches `src/modular_rag/` — both run standalone with just the one extra package
installed, per Lot 6's "disposable, outside the production path" requirement.

- [`langgraph_spike.py`](langgraph_spike.py)
- [`llamaindex_spike.py`](llamaindex_spike.py)

Both were actually executed against the installed package versions above (not written from
memory of an older API) — several early assumptions failed on first run and were corrected
against real error output; see the "surprises" callouts below.

## Capability checklist and evidence

| Capability | LangGraph | LlamaIndex Workflows | Evidence |
|---|---|---|---|
| Ingest | N/A to either — both are retrieval-agnostic orchestration layers; ingestion stays native per ADR-0005 regardless of engine choice | N/A, same reasoning | — |
| Answer | Works — `StateGraph` with typed state dict, conditional edges | Works — `Workflow` with typed `Event` subclasses matched by return type | Both spikes, check 1 |
| Evidence/citations | Passed through cleanly | Passed through cleanly | Both spikes, check 1 |
| Streaming | **Automatic, zero instrumentation**: `.stream(stream_mode="updates")` yields every node's full state delta with no extra code | **Opt-in only**: `stream_events()` only surfaces `StartEvent`/`StopEvent` by default — intermediate custom events (`RoutedEvent`, `RetrievedEvent`, ...) never appeared despite being real typed events flowing between steps; would need explicit `ctx.write_event_to_stream()` per event to expose them | Both spikes, check 3. Confirmed by running, not assumed — the LlamaIndex spike's check 3 printed only one `StopEvent`, which surprised me until I checked how `stream_events()` actually sources events |
| Cancellation | **No native cancel API.** Cancelling the wrapping `asyncio.Task` does raise `CancelledError` for both an async node (`await asyncio.sleep`) and a sync-blocking node (`time.sleep` inside a thread-pool-dispatched sync function) — but for the sync case, only the *caller* stops waiting promptly; whether the underlying blocking thread is actually killed or just abandoned was not verified here | **First-class `handler.cancel_run()`** (async method) — a real, discoverable, intentional API, not an asyncio-mechanics workaround | Both spikes, check 4. LangGraph spike's check 4b comment is explicit about the unverified thread-cleanup nuance — don't oversell this row |
| Governance interception | Clean — a guard node conditionally routes to a `blocked` node via `add_conditional_edges`; `generate` provably never runs (asserted in the spike) | Clean — a guard step returns a `Union[GuardPassedEvent, BlockedEvent]`; `generate` provably never runs | Both spikes, check 2 |
| Telemetry | DIY — each node appends a `TraceStepLike` to state manually; no built-in structured tracing beyond optional LangSmith integration (not spiked) | DIY — each step appends a `TraceStepLike` to an instance list manually; `llama_index_instrumentation` ships as a real dependency but wasn't spiked — worth a closer look in Lot 7 before ruling it out | Both spikes, check 1 |
| Deployment/footprint | **~4.8 MB** installed (`langgraph` + `langgraph_sdk`); depends on `langchain-core` — real transitive coupling to the LangChain ecosystem even though only `langgraph` itself was installed | **~30 MB** installed (`llama_index` + `workflows` + `llama_index_instrumentation`); broader "core" dependency list (`aiohttp`, `sqlalchemy`, `nltk`, `tiktoken`, `networkx`, ...) even before any integration package | `pip show`, `du -sh` on both — see commit for exact commands |
| License | MIT | MIT | `pip show` `License-Expression` field, both |

## Selection matrix (weighted toward what ADR-0005 actually delegates)

ADR-0005 delegates *generic orchestration* specifically — not ingestion, not retrieval, not
governance (those stay owned). So the rows that matter most for this decision are streaming,
cancellation, telemetry-friendliness, and footprint/coupling — the actual mechanics of running
someone else's orchestration engine underneath our owned control plane.

| Dimension | Winner | Why it matters here |
|---|---|---|
| Streaming (zero-instrumentation visibility) | LangGraph | We need full step-level visibility for the audit trail (owned capability, Lot 10) — opt-in-only streaming means remembering to instrument every step correctly, a compliance footgun if someone forgets |
| Cancellation | LlamaIndex | A real, intentional API beats relying on asyncio Task mechanics we'd have to document and defend ourselves |
| Footprint/coupling | LangGraph | ~6x smaller; `langchain-core` coupling is a real but minor cost, easily isolated behind the `DocumentEngine` port (Lot 7) so it never leaks into `core`/`contracts` |
| Structural legibility | LangGraph | Explicit node/edge graph maps more directly onto this project's own explicit registry+manifest wiring philosophy than event-type-driven implicit step matching — matters for whoever has to explain "what will this governed pipeline actually run" to a reviewer |
| Governance interception | Tie | Both handled it cleanly with ordinary control flow |

**Net read:** LangGraph wins 3 of 5 weighted dimensions, loses cancellation clearly. Not a
landslide — LlamaIndex's `cancel_run()` is a genuinely better piece of API design than anything
LangGraph offers here. See [ADR-0006](../../adr/0006-external-engine-selection.md) for the
recommendation and how it accounts for that gap.

## Rejected without a spike: Haystack

The user narrowed the spike to LangGraph + LlamaIndex this session (recorded decision,
2026-08-04) specifically because Haystack overlaps heavily with LlamaIndex's ingestion/retrieval
strengths without adding a distinct answer to the actual question this lot is deciding —
*which engine to delegate generic multi-agent orchestration to*, per ADR-0005. If LlamaIndex
loses this round, Haystack is not an obviously stronger fallback on the orchestration dimension
specifically and would need its own justification to spike later, not an assumption that it's
next in line.

## Deployment capability — not spiked, assessed from documentation only

Per the plan, "deployment" is one of the eight dimensions but wasn't exercised at runtime here
(no target deployment platform is decided yet — `docs/refactoring-plan.md` §10, still an open
question). Both ship as plain Python libraries with no required separate server process for the
orchestration layer itself (LangGraph's optional hosted "LangGraph Platform" and LlamaIndex's
optional "LlamaCloud" are managed add-ons, not requirements). Neither is a blocker either way;
revisit properly once Lot 16c's deployment target is fixed.
