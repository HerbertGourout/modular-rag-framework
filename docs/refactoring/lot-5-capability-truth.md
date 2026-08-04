# Lot 5 — Capability Truth and Runnable-Manifest Classification

**Status:** COMPLETE — Phase A (Lots 0-5) is now fully COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 1 (product boundary), Lot 3 (CI to validate runnable commands in)

## What was done

Corrected delivered/security/compliance claims across 6 files, using the concrete facts
established by Lots 3-4 (real dependency install, real test run, real bug findings) rather than
re-guessing from the code:

- **`README.md`**: status badge `v1 stable` → `pre-alpha` (matches `pyproject.toml`'s own
  `Development Status :: 2 - Pre-Alpha` classifier, which the badge directly contradicted); test
  count badge `98/98` → `250 passing` (current, from Lot 4's final run); REST API launch snippet
  replaced with a working non-`--factory` invocation (`create_app()` requires a manifest-path
  argument that bare `--factory` mode can't supply — confirmed by reading `api/__init__.py`);
  added an explicit warning that `POST /answer` returns 422 today (Lot 4 finding); "Project
  status" table reworded per-row instead of a blanket "V1 complete" claim, each caveat linking to
  the specific `docs/refactoring-plan.md` §2 gap; "Full observability" claim corrected to state
  that `Trace` is discarded unless a `telemetry` component is wired, which the manifest schema
  doesn't yet expose a way to do.
- **`docs/api/rest.md`**: same launch-command fix; `POST /answer` response example corrected from
  a fabricated `{"answer": ..., "model": ...}` shape to the real `AnswerResponse` shape
  (`text`/`citations`/`trace_id`, no `model` field); removed the documented `403 Forbidden` for
  guard blocks — confirmed the code has no such status anywhere, guard blocks currently surface
  as `500` like every other exception; `GET /retrieve` response corrected from a fabricated
  5-field shape (`chunk_id`/`doc_id`/`content`/`source`/`score`/`rank`/`retrieval_method`) to the
  real 3-field one (`chunk_id`/`score`/`content`, truncated to 300 chars) — verified against
  `api/__init__.py` and `tests/unit/api/test_api.py`.
- **`manifests/presets/*.yaml`** (all 5) + new **`manifests/README.md`**: classified as
  `RUNNABLE` (`local-hybrid-rag.yaml` only) or `BLUEPRINT` (the other 4), each with the specific
  reason read directly from `orchestration/registry.py`'s `wire()` method — not just "V2/V3/V4/V5
  scope" as an assumption. Two blueprint presets have concrete breakage beyond "not implemented
  yet": `multimodal-rag.yaml`'s `embedder.type: multimodal` isn't a registered factory at all
  (immediate `RegistryError`), and `secure-enterprise-rag.yaml` references two policy files that
  don't exist on disk plus an unresolved `${QDRANT_URL}` template (manifest interpolation is Lot
  9 scope, not implemented).
- **`docs/business-case.md`**: the "Complete audit trail" and "Multi-tenant isolation... no risk
  of cross-contamination" bullets — client/compliance-facing claims — corrected to state their
  actual current status (a `Trace` model and a `tenant` field exist; neither is enforced or
  persisted today) with an explicit instruction not to cite either claim in a client or
  compliance context until the owning lot (10, 11b) is `COMPLETE`.
- **`scripts/check.sh`** + **`.github/workflows/ci.yml`**: added a new validation step —
  `load_pipeline('manifests/presets/local-hybrid-rag.yaml')` — so the one manifest classified
  `RUNNABLE` is mechanically checked on every `check.sh full` and every CI run, not just asserted
  in prose. `check.sh full` renumbered 6→7 steps accordingly.

## Verification

- `./scripts/check.sh full` — all 7 steps pass, including the new manifest-validation step.
- 250 tests still pass (202 unit + 48 contract) — this lot touched no test-covered source code,
  only docs, manifests, and the check script/CI config.
- Manually re-read every corrected claim against the actual code it describes (not just against
  memory of an earlier read) before writing it down — the same discipline as Lots 3-4.

## Lot 5 acceptance (per `docs/refactoring-plan.md` §6)

"No unsupported delivered/security/compliance claim; runnable docs commands pass." Every command
shown in `README.md`'s "Getting started" section and `docs/api/rest.md` now either works as
written or is explicitly flagged as broken with a pointer to the evidence. Every manifest's
runnability claim is now both documented and CI-checked for the one preset claimed runnable.

## Phase A closure

Lots 0-5 are now all `COMPLETE`. Phase A's goal — programme control, an accepted product-
boundary ADR, realigned Claude configuration, a reproducible environment with real CI gates,
characterization coverage across the public surface, and accurate capability claims — is met.
Phase B (Lots 6-10: engine-fit spike, `DocumentEngine` contracts, native adapter, versioned
config, trace/audit foundation) is the next phase in `docs/refactoring-plan.md`, not started.
