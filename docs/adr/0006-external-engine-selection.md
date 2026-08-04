# ADR-0006 — External Engine Selection: LangGraph

**Status:** Proposed
**Date:** 2026-08-04
**Authors:** Herbert Gourout (drafted by Claude Code from an executed spike; recommendation
requires Herbert Gourout's explicit sign-off before moving to Accepted — see §"Decision record")

---

## Context

[ADR-0005](0005-document-ai-control-plane-boundary.md) delegates generic multi-agent
orchestration, tool-calling, and dynamic flow compilation to a selected external engine instead
of building them natively. `docs/refactoring-plan.md` Lot 6 requires picking that engine via a
time-boxed spike comparing real, executed code — not a documentation-only comparison — against
a representative use case and a fixed capability checklist (ingest, answer, evidence, streaming,
cancellation, governance interception, telemetry, deployment).

Per the user's explicit scoping decision this session (2026-08-04), the spike compared
**LangGraph** and **LlamaIndex Workflows** — Haystack was deliberately excluded from this round
(see `docs/refactoring/lot-6-spike/README.md` for why).

Full spike evidence, the executed code, and the full selection matrix:
[`docs/refactoring/lot-6-spike/`](../refactoring/lot-6-spike/).

---

## Decision

**Recommend LangGraph** (currently 1.2.10) as the external engine `DocumentEngine` (Lot 7)
adapts to.

### Why, in one paragraph

Of the dimensions ADR-0005 actually delegates — orchestration mechanics, not ingestion or
governance, which stay owned — LangGraph wins on the three that matter most for this project
specifically: automatic, zero-instrumentation step-level streaming (directly useful for the
owned audit trail, Lot 10, without relying on every future contributor remembering to
instrument each step correctly); a roughly 6x smaller install footprint; and a graph model
(explicit nodes, explicit conditional edges) that maps more legibly onto this project's own
explicit registry+manifest wiring philosophy than LlamaIndex's event-type-driven implicit step
matching. It loses clearly on one dimension — LlamaIndex's `handler.cancel_run()` is a real,
first-class cancellation API, where LangGraph offers no native equivalent and relying on
`asyncio.Task.cancel()` leaves an unverified question about whether a blocking synchronous node
is actually interrupted or just abandoned in a background thread.

### Why the cancellation gap doesn't change the recommendation

Lot 7 already has to define engine-neutral `ExecutionContext` and cancellation semantics as part
of the `DocumentEngine` port — that contract has to work across *any* future engine, not just
whichever one is picked today. Building a documented, tested cancellation contract on top of
`asyncio.Task` cancellation (a well-understood, portable Python primitive) is normal Lot 7 work
either way; LlamaIndex's nicer native API would only have saved us from writing that contract
ourselves, not from needing one.

### Full evidence

See the selection matrix in [`docs/refactoring/lot-6-spike/README.md`](../refactoring/lot-6-spike/README.md#selection-matrix-weighted-toward-what-adr-0005-actually-delegates) —
this ADR summarizes it, that document has the row-by-row reasoning and the actual executed
spike output.

---

## Consequences

### Positive

- Smallest reasonable footprint for the delegated-orchestration adapter, consistent with this
  project's own stated anti-lock-in, anti-bloat posture (ADR-0005 §Context: *"a small team...
  cannot out-execute [LangChain/LlamaIndex/Haystack] on generic agent runtimes"* — picking the
  lighter dependency reduces how much of that ecosystem we drag in even as a delegatee).
- LangGraph's explicit graph structure is easier to statically inspect for a governance
  reviewer ("what will this pipeline actually execute") than an implicit event-matching model —
  directly useful for the owned governance capability (ADR-0005 §5.1).
- Automatic per-node streaming reduces the instrumentation burden on whoever builds the Lot 10
  audit/trace sink against this engine.

### Negative / Risks

- `langgraph` depends on `langchain-core`, a real (if currently thin) transitive dependency on
  the LangChain ecosystem — must stay isolated behind the `DocumentEngine` port (Lot 7) so it
  never leaks into `core`/`contracts`, per the existing hexagonal layering rules.
- No native cancellation API — Lot 7 must design and test the cancellation contract itself
  rather than adopting one off the shelf. Explicitly verify thread-level cleanup behavior for
  sync-blocking nodes before relying on cancellation semantics in production (flagged as
  unverified in the spike evidence, not confirmed either way).
- LangGraph is more chat/agent-oriented by design; if a future need emerges for deep
  ingestion-side orchestration (unlikely given ADR-0005 keeps ingestion native), LlamaIndex's
  broader tooling wouldn't be available without a second adapter.

### Mitigations

- The `DocumentEngine` port (Lot 7) is designed engine-neutral specifically so this choice is
  swappable — ADR-0005 §5.6 requires a second adapter to prove the abstraction isn't
  lowest-common-denominator before Lot 15 production work is considered complete. If LangGraph
  turns out wrong in practice, the cost of reversing this decision is bounded by that design
  goal, not a rewrite.
- Cancellation contract gets explicit test coverage in Lot 7's semantic conformance suite,
  including the sync-blocking-node case the spike flagged as unverified.

---

## Open decisions (deferred, not resolved by this ADR)

- Whether Haystack deserves its own spike later — not ruled out permanently, just not this
  round (see `docs/refactoring/lot-6-spike/README.md`).
- LlamaIndex's `llama_index_instrumentation` package was noticed as a real dependency during the
  spike but never evaluated — worth a look during Lot 7/10 even though LlamaIndex itself wasn't
  selected, in case its ideas (not its code) inform the audit/trace design.
- Exact LangGraph version to pin — this ADR evaluated 1.2.10; Lot 7 should re-confirm before
  freezing the contract, since both packages ship frequent releases.

---

## Decision record

**Decision:** Recommend LangGraph as the Lot 7 `DocumentEngine` port's initial adapter target.

**Date:** 2026-08-04

**Status:** Proposed. Per `docs/refactoring/lot-0-baseline.md` §2, Herbert Gourout is sole
decision authority — but unlike ADR-0005 (whose substance was discussed at length before
acceptance), this is a fresh technical recommendation from an executed spike he has not yet
personally reviewed. Requires his explicit confirmation (or a redirect) before moving to
`Accepted` and unblocking Lot 7.

**Next:** Await confirmation, then Lot 7 (`DocumentEngine` contracts, engine-neutral, LangGraph
as the first adapter).
