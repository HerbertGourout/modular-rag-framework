---
name: validate-architecture
description: Validate a change against current hexagonal boundaries, contracts, composition, manifests, and engine capabilities
---

# Validate Architecture

Use this workflow after a change that affects contracts, domains, adapters, orchestration,
composition, manifests, or public interfaces.

## 1. Read the authoritative boundaries

- Root `CLAUDE.md`
- `docs/architecture/module-model.md`
- The `CLAUDE.md` in every affected source module
- The accepted ADR governing the change
- ADR-0015 when the change concerns portable assurance; remember that its direction is accepted
  but its public contracts are not implemented

Do not treat roadmap items or proposed ADRs as implemented contracts.

## 2. Run the strict layering checker

```powershell
.\.venv\Scripts\python.exe scripts\check_layering.py --strict
```

Interpret results using the repository model:

- `core` imports only itself;
- `contracts` imports only `core` and `contracts`;
- each domain imports `core`, `contracts`, and itself;
- `adapters` imports `core`, `contracts`, and `adapters`;
- `orchestration` imports `core`, `contracts`, and `orchestration`;
- `app` is the concrete composition root;
- `api` and `cli` enter through `app`.

Do not replace violations with a broader baseline unless the maintainer explicitly accepts a documented
exception.

## 3. Verify contracts and models

Open the actual Protocol and model definitions. Do not rely on similarly named examples in old
issues or external libraries. For every contract change verify:

- an accepted ADR and explicit compatibility policy;
- all implementations and runtime-checkable conformance tests;
- public exports and type annotations;
- migration behavior for existing manifests/callers;
- no vendor type leaking into `core` or `contracts`.

Prefer additive capability Protocols when that preserves compatibility. Do not invent suffixed
`V2` interfaces without a concrete migration need.

## 4. Verify composition and manifest wiring

A built-in implementation must be registered in `src/modular_rag/app/default_factories.py` and
selected through the existing YAML schema. Check:

- role/type-name registration;
- configuration parsing and environment substitution;
- capability validation before `wire()`;
- preset and blueprint status;
- tests for unknown and unsupported configurations.

There is no global `COMPONENT_REGISTRY` or `registry.get_component()` API.

## 5. Verify engine semantics

The native `RAGEngine` is the reference execution. `LangGraphEngineAdapter` supports a bounded
subset and must declare capabilities honestly. A new or changed control needs either tested parity
for every adapter claiming it or fail-fast rejection for unsupported combinations.

Do not recreate generic routing/flow compilation in the native engine: ADR-0005 delegates it
through `DocumentEngine`. Do not implement ADR-0015's existing-application adapter
(`adapters/applications/`, Lot 22) opportunistically — its contract (`contracts/application.py`,
ADR-0018) already exists but the adapter does not. Lot 20 provider egress (ADR-0016) and Lot 21
assurance conformance (ADR-0017) are both shipped, not planned.

## 6. Verify observability and failure behavior

- Use the real `TraceStep` and OTel/Meter contracts.
- Avoid duplicate stage and request-level signals.
- Preserve fail-closed tenant, policy, and mandatory governance behavior.
- Do not expose sensitive content in logs, traces, reports, or readiness errors.
- Align readiness criticality with actual query-serving failure behavior.

## 7. Run focused validation

Run affected unit, contract, bootstrap, manifest, and parity tests, then:

```powershell
.\scripts\check.ps1 quick
.\scripts\check.ps1 full
git diff --check
```

Do not run provider-backed integration/e2e tests without confirmed services and credentials.

## Report format

Report each item as `PASS`, `FAIL`, or `NOT APPLICABLE`, with `file:line` evidence for failures:

1. layering;
2. contracts and compatibility;
3. composition and manifests;
4. engine capabilities and parity;
5. failure/security/observability behavior;
6. tests and documentation.

Separate current implementation defects from proposed roadmap work. Do not pass a change that
silently ignores a declared capability or control.
