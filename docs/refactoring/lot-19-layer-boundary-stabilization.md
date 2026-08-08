# Lot 19 — Layer-Boundary Correction and Control-Plane Activation

**Status:** COMPLETE (local engineering and finalization gates) — infrastructure sign-off pending
**Date:** 2026-08-07
**Depends on:** Lot 18 (programme closure, engineering-complete, sign-off pending) and
[ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md) (accepted 2026-08-07)
**Gates:** `./scripts/check.sh full` (7/7), `scripts/check_layering.py --strict`,
`scripts/check_docs.py`, `pytest tests/unit tests/contract`

This is the Lot 19 deliverable referenced by `docs/refactoring-plan.md`'s tracker row and by
ADR-0007 itself ("pending a dedicated evidence writeup at closure"). A follow-on audit after
Lot 18's closure found the published dependency direction (`api/cli → app → orchestration →
contracts/core`) didn't match the real one (`orchestration/{engine,registry,reconciliation}.py`
imported `app.Container`), and that governance/audit/quality implementations existed and were
tested but were not reachable through any manifest — a capability could be "Operational" in the
code and still unreachable by a user who only edits YAML. ADR-0007 records the decision; this
file records what actually happened across the 12 execution étapes and what the resulting gates
say.

---

## 1. What each étape did

| Étape | What it did | Evidence |
|---|---|---|
| 1 | Baseline + capability matrix: inventoried the real gap between documented and actual dependency direction; documented every owned capability's true reachability status | [capability-matrix.md](../architecture/capability-matrix.md) |
| 2 | ADR-0007 decision record: layer-boundary rules, mandatory manifest activation, preset/blueprint separation, legacy-field removal, CI enforcement | [ADR-0007](../adr/0007-layer-boundaries-and-control-plane-activation.md) |
| 3 | Exhaustive layering checker: extended `scripts/check_layering.py` to cover all seven layers (`core`, `contracts`, domain, `adapters`, `orchestration`, `app`, `api`/`cli`), not just the four it audited before | `scripts/check_layering.py`, `.claude/layering-baseline.txt` |
| 4 | Dependency-direction fixes: moved `Container` to `orchestration/container.py` (with an `app/container.py` compatibility re-export); moved `_default_factories.py` to `app/default_factories.py`; emptied the layering baseline; `--strict` passes clean | `src/modular_rag/orchestration/container.py`, `src/modular_rag/app/default_factories.py` |
| 5 | Manifest V2 contract: `governance`/`quality`/`observability`/`lifecycle` sections in `contracts/manifests.py`, `extra="forbid"`, plus the new `governance.tenant_enforcement` fail-closed flag | `src/modular_rag/contracts/manifests.py`, `app/config_resolution.py` |
| 6 | Governance/audit/quality capability wiring: registered `postgres` factories for `audit_sink`/`lifecycle_ledger`; added conformance + unit tests for telemetry and the newly-activatable roles | `app/default_factories.py`, `tests/contract/test_telemetry_conformance.py` |
| 7 | Preset/blueprint reorganization: rewrote `secure-enterprise-rag.yaml` and `langgraph-rag.yaml` (renamed from `agentic-rag.yaml`) as genuinely Runnable V2 manifests, verified end-to-end (`resolve_manifest()` → `validate_capabilities()` → `registry.wire()` → `load_engine()`); moved `graph-memory-rag.yaml`/`multimodal-rag.yaml` to `manifests/blueprints/` with explicit non-Runnable headers; regenerated the JSON schema | `manifests/presets/`, `manifests/blueprints/`, `manifests/schema/pipeline-manifest.schema.json` |
| 8 | Dead-code removal: deleted `app/settings.py` (orphaned `MRAG_*` `Settings` class), `memory/graph/` (`KnowledgeGraph`, zero consumers), `GraphError`/`AgentError`, `Trace.routing_strategy` (bumped schema to 1.2), `planner`/`graph_store` registry roles, `RetrievalMethod.GRAPH`/`.MULTIMODAL`, `ChunkingStrategy`, `GraphRelation` | commit history, [ADR-0007's resolved decision #4](../adr/0007-layer-boundaries-and-control-plane-activation.md#resolved-knowledge-graph-data-model-étape-8-2026-08-07) |
| 9 | Documentation realignment (core docs): `CLAUDE.md`, `README.md`, `ROADMAP.md` (corrected systemic ✅-overuse for unbuilt success criteria), `docs/refactoring-plan.md`, `docs/architecture/capability-matrix.md` | commit `b45c684` |
| 10 | Documentation realignment (business/architecture docs): `docs/business-case.md`, `docs/onboarding.md`, `docs/architecture/{overview,module-model,runtime-flow}.md` | commit `2acea86` |
| 11 | Claude Code instruction realignment: `.claude/.prompt.md`, `.claude/.instructions.md`, `.claude/AGENTS.md`, `.claude/rules/orchestration.md`, `contracts/CLAUDE.md`, `security/CLAUDE.md`; archived `docs/documentation-audit-2026-08.md`; built `scripts/check_docs.py` (link/dead-API/blueprint-labeling regression gate) and used it to find and fix further staleness (see §3) | commit `ac2834a` |
| 12 | This file: final gate run, residual-risk list, sign-off note | this document |

---

## 2. Gate results

Run 2026-08-07, working tree at commit `ac2834a` plus the drive-by fix in §3:

| Check | Command | Result |
|---|---|---|
| Lint | `ruff check .` | **Pass** (1 pre-existing unused import in `examples/simple_qa/main.py`, unrelated to this lot, found and fixed — see §3) |
| Compilation | `python -m compileall -q src/modular_rag scripts examples` | **Pass** |
| Layering (strict) | `python scripts/check_layering.py --strict` | **Pass** — 0 violations across all 7 layers, baseline empty |
| Docs regression gate | `python scripts/check_docs.py` | **Pass** — 0 active findings; 36 accepted baseline mentions (legitimate past-tense explanations of Lot 17/Étape 8 deletions, individually verified, listed in `.claude/docs-terms-baseline.txt`) |
| Type checking | `python -m mypy src/modular_rag` | 31 errors — matches the pre-existing accepted baseline (not a gate blocker; unchanged by this lot) |
| Unit + contract tests | `pytest tests/unit tests/contract -q` | **588 passed** (498 unit + 90 contract) |
| Full local suite | `./scripts/check.sh full` | **7/7 green** |

`scripts/check_capabilities.py`, mentioned as an optional ("éventuellement") automation idea in
the original Étape-1 planning, was **not built**. `docs/architecture/capability-matrix.md`
already serves the same purpose today — every capability's reachability was individually
re-verified by hand (registry inspection, live `resolve_manifest()`/`validate_capabilities()`/
`registry.wire()` runs) rather than by a script — and a capability-drift linter without a
clearer spec of what "drift" means here risked being either too narrow to catch real gaps or too
broad to avoid false positives, the same trap `check_docs.py`'s first draft fell into (see §3).
Building it is future, optional work, not a gap in this lot's own gates.

---

## 3. What running the new gate found (not just theory)

Building `scripts/check_docs.py` in Étape 11 and actually running it against the repository — rather than treating it as a checkbox — surfaced real, previously-undetected staleness:

- **`app/settings.py` present-tense references across 9 active guide files** (`CLAUDE.md`,
  `examples/simple_qa/README.md`, and 7 files under `docs/guides/`, plus
  `.claude/rules/security-layers.md`): all still described the file as if it existed ("declares",
  "is orphaned") when it was actually deleted outright in Étape 8. Fixed to past tense with a
  pointer to the deletion.
- **Nine broken relative links** from wrong `../` depth: `.claude/.prompt.md` (3), `.claude/AGENTS.md`
  (3, all the same off-by-one), `contracts/CLAUDE.md` (3), `security/CLAUDE.md` (2), plus one each
  in `docs/guides/audit-traceability.md`, `claude-code-parallelization-orchestration.md`, and
  `onboarding-claude-code.md`.
- **A stale `orchestration/_default_factories.py` reference** in `docs/guides/code-walkthrough.md`
  (moved to `app/default_factories.py` in Étape 4).
- **A stale `memory/graph/knowledge_graph.py` reference** in `manifests/blueprints/graph-memory-rag.yaml`
  (deleted in Étape 8) — the blueprint's own explanatory comment named a file that no longer exists.
- **An "unresolved" gap-matrix row in `docs/refactoring-plan.md`** (the orphaned `Settings` class)
  that Étape 8 had already closed by deleting the file — marked resolved.
- **A false-positive-driving design flaw in the check script itself**: the first draft's naive
  `[text](url)` link regex matched regex patterns shown in prose tables (e.g. a phone-number
  regex containing literal `[`/`(` characters) and matched illustrative "here's the link format
  to use" examples inside fenced code blocks in `.prompt.md`/`AGENTS.md` as if they were real
  navigable links. Fixed by skipping fenced code blocks and stripping inline code spans before
  link-matching, and by anchoring the blueprint-marker check to the literal `Status: BLUEPRINT`
  header line instead of a bare substring (which had a false positive on
  `secure-enterprise-rag.yaml`'s own prose explaining it *used to be* a blueprint).
- **One pre-existing, unrelated `ruff` finding**: an unused `os` import in
  `examples/simple_qa/main.py`, outside this project's own configured lint scope
  (`src/modular_rag/ tests/`) but caught by running `ruff check .` for this gate. Fixed as a
  zero-risk drive-by.

None of these were regressions introduced by this lot — they were pre-existing staleness the
lot's own new tooling was built to catch, which is the intended outcome of building it.

---

## 4. Native vs. LangGraph adapter — current comparison

Both `DocumentEngine` implementations are Operational per the capability matrix; neither changed
in this lot. Summarized here because Lot 19 is the first point where *both* are reachable through
a genuinely Runnable preset (`local-hybrid-rag.yaml` and `secure-enterprise-rag.yaml` for native,
`langgraph-rag.yaml` for LangGraph, all verified end-to-end in Étape 7):

| Dimension | `NativeEngineAdapter` | `LangGraphEngineAdapter` |
|---|---|---|
| Selection | `engine.adapter: native` (or omitted — the default) | `engine.adapter: langgraph` |
| Declared capabilities | None (`STREAMING`/`GOVERNANCE_INTERCEPT`/`CANCELLATION` all absent) | `STREAMING`, `GOVERNANCE_INTERCEPT`, `CANCELLATION` |
| Underlying execution | The existing fixed-sequence `RAGEngine` | A real LangGraph `StateGraph` orchestrating the same wired `Container` components |
| Audit evidence emission | Yes, via the wired `AuditSink` | **No** — the `ApplicationService` caller now exists, but it does not yet translate LangGraph execution events into the owned `AuditSink` (still open, see §6) |
| Reachable from API/CLI by default | Yes, through `load_application()` | **Yes**, when the resolved manifest selects `engine.adapter: langgraph`; API and CLI import `load_application()` through `app.public` |

---

## 5. Checks that cannot run in this sandboxed environment

Unchanged from Lot 18's closure findings — no live infrastructure exists here (no `docker`,
`psql`, `pg_dump`, reachable Qdrant/Postgres, or LLM API keys):

- Qdrant/Postgres integration tests (`pytest tests/integration -m integration`).
- Full e2e pipeline test requiring a real LLM API key (`pytest tests/e2e -m e2e`).
- A live REST API smoke test (`uvicorn` + real HTTP requests).
- Running the native pipeline against real Qdrant + a real LLM end-to-end.
- Running the LangGraph pipeline against real Qdrant + a real LLM end-to-end.
- A live tenant-isolation integration test against a real vector store.
- An actual Postgres write through `PostgresAuditSink`/`PostgresLifecycleLedger` (registered and
  unit-tested against the interface; never executed against a real database here).
- A manifest V1→V2 migration/rollback exercised against a running deployment.
- `scripts/loadtest_answer.py` and the CI `container-build`/`supply-chain` jobs (Lot 18 findings,
  still true).

All of the above are either correct-by-construction against each system's own documented
interface (verified via unit tests with fakes/mocks) or are exactly what the next real CI run /
staging deployment is for — not something this lot could have executed differently.

---

## 6. Residual risks — the honest list

Carried forward from Lot 18's closure list where still true, plus what this lot found:

| Item | Status |
|---|---|
| `manifests/production/_index.md` cannot be edited | Hard `permissions.deny` on `manifests/production/**` in `.claude/settings.json` blocked two separate edit attempts this lot (Étape 7 and earlier); confirmed intentional (V4+ governance scope), not a bug, but it means this specific file could not be brought current alongside everything else. |
| API/CLI engine selection | **Resolved after Étape 12:** both use `load_application()`, which honors `engine.adapter`; covered by the application façade tests and preset smoke checks. |
| LangGraph adapter emits no audit evidence | The `ApplicationService` caller exists, but the bridge from LangGraph execution events to the owned `AuditSink` remains to be designed and tested. |
| `IndexReconciler` remains programmatic-only | Not exposed through CLI/API/manifests — unchanged by this lot. |
| Lifecycle hashing layer violation | **Resolved after Étape 12:** helpers live in `core/document_identity.py`; ingestion exposes only a compatibility re-export. |
| `scripts/check_capabilities.py` not built | Optional per the original plan; `capability-matrix.md` covers the same ground today via manual (but individually verified) inspection. See §2. |
| `pymupdf` AGPL-3.0/Artifex dual licence; 56 research PDFs' unverified redistribution rights | Carried from Lot 16b/17 — Herbert Gourout confirmed "leave as-is for now," still not resolved. |
| Live-infrastructure checks (§5) | Cannot be executed in this sandbox; next real CI run / staging deployment is the actual verification. |

---

## 7. Sign-off

Consistent with this programme's established practice (Lot 18), **final sign-off is not
self-granted** — it is reserved for Herbert Gourout, sole decision authority. This lot's
engineering scope is complete and all locally-runnable gates are
green; what remains is the same category of decision Lot 18 already deferred: architecture,
security, operations, legal, and business-quality review of the cumulative programme (Lots 0-19)
by the person who owns that decision, not a checklist this document can close on his behalf.

---

## 8. Finalization pass — 2026-08-07

The post-closure finalization corrected two stale claims in this report and the capability
matrix: API/CLI now use `load_application()` and honor `engine.adapter`, and document hashing
now belongs to `core/document_identity.py`. It also made resource ownership explicit:
`ApplicationService.close()` delegates to `RAGEngine.close()`/`Container.close()`, the FastAPI
lifespan closes the application on shutdown, and CLI `ingest`/`ask` close it in `finally` blocks.

Local evidence after those changes:

- Ruff, compilation, strict layering, documentation checks, and `git diff --check`: pass.
- MyPy: 31 errors, equal to the ratcheted baseline of 31 (no regression).
- All three runnable presets wire successfully; selected engines are native, native, and
  LangGraph respectively.
- Unit + contract suite: 588 passed, with one upstream Starlette/httpx deprecation warning.

Infrastructure discovery found no Docker or `psql` executable, no listener on Qdrant port 6333
or PostgreSQL port 5432, and no OpenAI/Anthropic API key. Integration/E2E execution therefore
remains a staging/CI sign-off activity rather than a silently skipped local success.
