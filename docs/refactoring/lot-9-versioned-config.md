# Lot 9 — Versioned Solution Configuration and Secret Resolution

**Status:** COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 7 (`DocumentEngine` port, for the new `engine` manifest section)

## What was done

- **Strict extra-field policy**: `model_config = ConfigDict(extra="forbid")` on `PipelineManifest`
  and `ComponentConfig`. A typo'd or unknown top-level field now fails validation instead of
  being silently ignored — closes the exact gap named in `docs/refactoring-plan.md` §2
  ("Component configuration accepts arbitrary dictionaries"). A component's own
  `config: dict[str, Any]` payload deliberately stays free-form — that's genuinely dynamic
  per-adapter-type configuration, not the same problem as unknown top-level manifest keys.
- **Four new optional v2 schema sections** on `PipelineManifest`: `engine` (adapter selection —
  "native" today, "langgraph" once Lot 15 lands), `governance`, `quality`, `observability`. All
  default to `None`, so every existing v1 manifest validates completely unchanged. Each section's
  docstring is explicit about what it does *not* yet do: populating `governance.tenant_enforcement`
  doesn't enforce anything until Lot 11b; `quality.gates` isn't checked until Lot 13;
  `observability.telemetry_sink` isn't wired until Lot 10. This lot delivers the *shape*, not the
  behavior those sections imply — recorded here so the gap isn't accidentally overclaimed later.
- **`app/config_resolution.py`** (new module, deliberately separate from `app/bootstrap.py` so
  existing `load_manifest()`/`load_pipeline()` callers are unaffected unless they opt in):
  - `interpolate()`: resolves `${VAR}` against `os.environ` and `secret://NAME` via a
    `SecretResolver` (new `contracts/secrets.py` Protocol). Closes the concrete gap found in
    Lot 5: `secure-enterprise-rag.yaml`'s `${QDRANT_URL}` was never interpolated before this.
  - `EnvSecretResolver`: the default, environment-variable-backed `SecretResolver` — a stand-in
    until a real backend (OpenBao, per `docs/refactoring/technology-candidates.md`) is wired as a
    second implementation of the same Protocol.
  - `resolve_manifest()`: layers preset YAML < environment-specific YAML < CLI overrides (shallow
    top-level merge, not deep field-by-field — documented reasoning for why in the function's own
    docstring) before interpolation and validation.
  - `validate_capabilities()`: dry-run check that every declared component `type:` exists in the
    registry, without instantiating anything. Required adding `ComponentRegistry.available_types()`
    as a new public method (`orchestration/registry.py`) — reaching into `_factories` directly
    from outside the class would have repeated the exact private-access pattern Lot 8 just spent
    effort eliminating.
  - `migrate_v1_to_v2()` / `rollback_v2_to_v1()`: purely additive/subtractive, proven to round-trip
    exactly (see Verification) against the one real runnable manifest.
- **`mrag validate <manifest>`** and **`mrag manifest-schema`** CLI commands
  (`cli/__init__.py`). `validate` runs schema + capability checks with no wiring/instantiation;
  `manifest-schema` prints the live JSON Schema.
- **`manifests/schema/pipeline-manifest.schema.json`**: committed, regenerable export of
  `PipelineManifest.model_json_schema()` — `additionalProperties: false` at the top level confirms
  the strict policy is reflected in the exported schema too, for IDE/editor tooling.

## Scoping decision worth recording

`load_pipeline()`/`load_manifest()` in `app/bootstrap.py` are **unchanged** — they do not call
`interpolate()` or the new strict validation. `resolve_manifest()` in `config_resolution.py` is
an additive, opt-in entry point. This means `secure-enterprise-rag.yaml` is *still* classified
`BLUEPRINT` in `manifests/README.md` — its `${QDRANT_URL}` interpolation problem is now solvable
by whoever wires `resolve_manifest()` into the default load path, but that wiring wasn't done
here, and the manifest's *other* problem (missing policy files, `wire()` never reading `policies`)
is untouched regardless. Consistent with Lot 8's own precedent: introduce new capability
alongside the stable path, don't change default behavior as a side effect of adding it.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 296 tests total (237 unit + 59 contract, up from 270).
- mypy baseline unchanged at 35.
- All 5 manifest presets re-validated against the new `extra="forbid"` policy — none broke (all
  five only ever used field names already in the schema).
- End-to-end migration proof against the actual runnable manifest, not just synthetic test data:
  `manifests/presets/local-hybrid-rag.yaml` → `migrate_v1_to_v2()` → validates as v2 → 
  `rollback_v2_to_v1()` → round-trips to a dict identical to the original file's parsed content.

## Lot 9 acceptance (per `docs/refactoring-plan.md` §6)

"Strict validation before startup; schema export; all runnable v1 manifests migrate and roll
back" — all three delivered. "All runnable v1 manifests" is exactly one manifest
(`manifests/README.md`'s classification from Lot 5), and it's the one proven above.

## Next

Lot 10 (versioned trace/audit foundation, PostgreSQL-backed per the earlier technology decision)
depends on Lot 7 and 9 both — the new `observability` manifest section is where that lot's sink
configuration will actually plug in.
