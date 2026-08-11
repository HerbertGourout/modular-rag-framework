# ADR-0009 — VectorIndexer sub-protocol and embedder/store dimension reconciliation

**Status:** Accepted
**Date:** 2026-08-11 (revised 2026-08-11 — second independent review pass, see §3 and §4 below)

## Context

`QdrantStore` took a `vector_size: int = 384` constructor default with no relationship to the
embedder actually wired alongside it in a manifest. Any preset whose embedder produced a
different dimension than 384 — `secure-enterprise-rag.yaml` and `langgraph-rag.yaml`, both
`BAAI/bge-base-en-v1.5` at 768 — silently got a 384-dimensional collection. The first real
`index()` call would fail with an opaque Qdrant-side vector-size error, or, worse, silently
accept truncated/padded vectors depending on the client version. Separately,
`local-hybrid-rag.yaml` (384-dim) and `langgraph-rag.yaml` (pre-existing default,
`bge-base-en-v1.5`, 768-dim) both pointed at a collection named `documents` on the same default
`localhost:6333` — two different dimensions sharing one collection name.

`Indexer` (`contracts/indexing.py`) has no notion of vector dimension: a lexical/BM25-style
store has none. Reconciliation is a capability specific to dimension-sensitive stores, not a
property every `Indexer` implementation can meaningfully support.

## Decision

1. **`VectorIndexer(Indexer, Protocol)`** — a new, narrower, opt-in sub-protocol in
   `contracts/indexing.py` with two methods, `bind_embedder(embedder: Embedder) -> None` and
   `ensure_vector_size(dimensions: int) -> None`. Every existing and future `Indexer` that is not
   dimension-sensitive is completely unaffected: it does not implement `VectorIndexer`, and
   `ComponentRegistry.wire()` only acts on stores that do (`isinstance(store, VectorIndexer)`, a
   pure in-memory Protocol check on `@runtime_checkable`, no network call). This keeps
   orchestration free of any Qdrant-specific import — it only knows the generic `VectorIndexer`
   contract. `bind_embedder()` is the hand-off point: `wire()` calls it with the wired `Embedder`
   once, and the implementation decides internally whether to reconcile immediately or defer (see
   §3). An earlier version of this decision had `wire()` write an undocumented private
   `_embedder` attribute directly instead of calling a protocol method — a structurally
   conforming `VectorIndexer` could pass `isinstance()` while silently ignoring that attribute,
   rejecting it via `__slots__`, or reusing the name for unrelated state, so the protocol
   captured nothing about the actual reconciliation hand-off (Codex review, second pass). Both
   methods are now real, declared members every implementation must provide.

2. **Reconciliation policy**, implemented by `QdrantStore.ensure_vector_size()`:
   - If the manifest's `indexer.config.vector_size` was left unset, adopt the wired embedder's
     `dimensions` as the store's real vector size (`derive`).
   - If `vector_size` was set explicitly, compare it against the embedder's `dimensions` and
     raise `core.errors.ConfigurationError` on any mismatch (`validate`). A manifest that
     declares one dimension while its embedder produces another is a configuration error, not
     something to silently paper over.
   - A collection that already exists in Qdrant (created by an earlier run, a different
     manifest, or before this check existed) is never recreated — `_ensure_collection()`
     additionally compares the *live* collection's real vector size against the store's
     reconciled `vector_size` and raises `ConfigurationError` before any upsert if they differ.
     Deriving/validating at wiring time alone only protects the very first collection creation;
     this closes the gap for a stale, already-populated collection.
   - A Qdrant collection configured with **named vectors** (`dict[str, VectorParams]` instead of
     a single unnamed `VectorParams`) has no single `.size` to compare against.
     `QdrantStore` never creates named-vector collections itself, so this can only happen against
     a collection created by something else; it is rejected with a clear `ConfigurationError`
     rather than an opaque `AttributeError`, and named vectors otherwise remain unsupported by
     this store.

3. **When reconciliation runs — the lazy/custom-embedder policy.** `ComponentRegistry.wire()`
   does not call `embedder.dimensions` directly, and does not decide when reconciliation happens
   — it only calls `store.bind_embedder(embedder)` once wiring confirms
   `isinstance(store, VectorIndexer)`. `QdrantStore.bind_embedder()` stores the reference;
   `QdrantStore._get_client()` calls `ensure_vector_size(self._embedder.dimensions)` itself, the
   first time it actually needs a live client — immediately before `_ensure_collection()`, and
   therefore still strictly before any collection is created or used. A different `VectorIndexer`
   implementation could instead reconcile eagerly, inside its own `bind_embedder()` — the
   protocol only requires that reconciliation happen before collection creation/use, not that
   every implementation defer it the same way `QdrantStore` does.

   This split matters because `Embedder.dimensions` is not always cheap: `HuggingFaceEmbedder`
   answers instantly for a small static table of known model names, but for any other model name
   it must load the real `sentence-transformers` model to ask it. An earlier version of this
   change called `embedder.dimensions` unconditionally inside `wire()`, which meant every
   `load_pipeline()`/`load_engine()`/`load_application()` call — i.e. every process startup —
   would force a real model load or download for any embedder outside that static table, even if
   the pipeline never went on to answer a query. That directly violates the lazy-import
   invariant (`CLAUDE.md` §05.7: heavy dependencies load on first real use, not at wiring time).
   Deferring the call into the store's own already-lazy `_get_client()` path restores that
   invariant for every embedder, known or custom, while keeping the "reject before collection
   creation/use" guarantee intact — the check simply moves from "at wiring" to "at the first
   real index/retrieve/delete/clear/list call," which was always where the network-touching half
   of this guarantee (the existing-collection check above) already lived.

4. **Fail-closed on retry, not just on first attempt.** `QdrantStore._get_client()` does not
   publish `self._client` until `_ensure_collection()` succeeds. An earlier version assigned the
   newly constructed `QdrantClient` to `self._client` *before* calling `_ensure_collection()`; if
   that call raised (a dimension or named-vector mismatch), the exception propagated correctly on
   the first call, but `self._client` was already non-`None` — a caller that caught the error and
   retried would find `_get_client()`'s `if self._client is None:` guard already false, skip
   `_ensure_collection()` entirely on every subsequent call, and proceed against the rejected
   collection (Codex review, second pass). `self._client` is now reset to `None` in an
   exception handler around `_ensure_collection()` before re-raising, so a retry re-validates
   from scratch instead of silently bypassing the guarantee after the first failure.

## Consequences

- Non-vector `Indexer` implementations (present or future) need no changes and are not
  Protocol-checked against `VectorIndexer` at all.
- `bge-small-en-v1.5` → 384, `bge-base-en-v1.5` → 768 are both derived correctly for all three
  shipped presets; `secure-enterprise-rag.yaml` and `langgraph-rag.yaml` no longer silently get
  a 384-dim collection.
- An explicit `indexer.config.vector_size` that disagrees with the wired embedder now fails with
  a clear `ConfigurationError` — at the first real store operation, not necessarily at `wire()`
  return, for embedders whose dimension requires a model load. Known models remain effectively
  immediate, since `HuggingFaceEmbedder`'s static table and `OpenAIEmbedder`'s fixed dimensions
  are both free to read regardless of when they're called.
- `langgraph-rag.yaml`'s collection rename (`documents` → `langgraph_documents`) is a breaking
  change for any deployment that already indexed data under the old name; see the operational
  migration note added alongside this ADR.
- A future vector store adapter that wants this reconciliation implements both `VectorIndexer`
  methods — `bind_embedder()` and `ensure_vector_size()`; one that doesn't implement the protocol
  at all is simply never asked to reconcile anything. `isinstance(store, VectorIndexer)` alone
  cannot verify an implementation's *internal* behavior (e.g. that it actually calls
  `ensure_vector_size()` from somewhere), the same limitation every other Protocol in this
  codebase has — but it can no longer be satisfied by an object that merely happens to share a
  private attribute name with `QdrantStore`, since there is no private attribute in the contract
  anymore.
- A retry after a failed `_get_client()` call now correctly re-validates instead of silently
  reusing a client that was never actually checked against a live collection.
