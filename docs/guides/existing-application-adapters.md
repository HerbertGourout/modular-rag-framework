# Existing-Application Adapter Guide

How to wrap an existing application behind the `DocumentEngine` port, following
[ADR-0018](../adr/0018-existing-application-adapter-boundary.md). The only adapter today is the
demo pilot `existing-graph`; it wraps a synthetic app and is **not** evidence that a real client
application has been wrapped.

## Reference implementation

| Piece | Path |
|---|---|
| Contract | `src/modular_rag/contracts/application.py` |
| Adapter | `src/modular_rag/adapters/applications/existing_graph/adapter.py` |
| Synthetic app | `examples/existing_graph_app/app.py` |
| Preset | `manifests/presets/existing-graph-app.yaml` |
| Composition branch | `src/modular_rag/app/bootstrap.py` (`_load_existing_graph_adapter`) |
| Harness fixture | `tests/contract/test_engine_conformance.py` (`_existing_graph_fixture`) |

## Design rules

1. **Identity comes only from `ExecutionContext`.** Tenant claims made by the application are
   inert metadata under `metadata["application"]`.
2. **Control points are hooks, not wrappers.** The application exposes hooks at retrieval and
   pre-model; the adapter scopes results by tenant, preserves each document's classification, and
   checks the egress policy for every distinct classification (including unclassified).
   Fail closed: no policy, unknown label, or any denial denies the call.
3. **The adapter owns audit completion.** A lost start or success event ends in `StorageError`
   and the result is withheld.
4. **The profile is derived, never declared.** `conformance_report()` is capped by
   `evidence_ceiling(profile)`; unsupported capabilities stay `UNSUPPORTED`
   (`astream` raises `EngineCapabilityError`).
5. **Startup gate (§14).** `registry.application_assurance_error` runs at load time and raises
   `ConfigurationError` if the manifest's `assurance.min_level` is not met.

## Loading and the allow-list

The application is named in `engine.config.application` as `module:callable`. The composition
root accepts only modules under the hard-coded prefix `examples.`, plus prefixes from the
operator's environment variable `MRAG_APPLICATION_MODULE_PREFIXES`. A manifest can never extend
its own allow-list. There is deliberately **no generic adapter registry**; adding one requires
its own ADR.

## Registering in the conformance harness

In `tests/contract/test_engine_conformance.py`, add a factory to `_FIXTURE_FACTORIES` returning an
`_EngineFixture(name, engine, context, probes)`. Every claimed status needs a probe at that rung
(`observed`, `verified`, `enforced`); `collect_claim_failures` rejects unprobed claims. Use
`_existing_graph_fixture` (real adapter) and `_foreign_fixture` (behavioural fixture) as models.

## Honest limits

- Demo pilot only: no real client application, no comparative measurement.
- The human architecture/security decision gate for Lot 22 is still open.
- Integration and e2e suites are not covered by this fixture.
