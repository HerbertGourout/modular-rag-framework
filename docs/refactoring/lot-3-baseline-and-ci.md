# Lot 3 — Reproducible Baseline and Minimum CI Gates

**Status:** COMPLETE
**Date:** 2026-08-04
**Depends on:** Lot 0
**Verification:** `./scripts/check.sh full` passes end-to-end locally (Windows, Git Bash,
Python 3.12.10, all 6 steps green).

## What was done

1. **Local environment.** Created `.venv` (Python 3.12.10, satisfies `requires-python >=3.11`)
   and installed with `pip install -e ".[v1,dev]"` per `CLAUDE.md`'s documented quick-start.
   Previously no `.venv` existed anywhere and the system Python had none of the project's
   dependencies — this is the first time the declared dev toolchain has actually been run.
2. **`pytest-cov` gap closed.** Added `pytest-cov>=5.0` and `build>=1.2` to the `dev` extra in
   `pyproject.toml`. Both GitHub and GitLab CI configs already invoked `--cov` flags without
   this dependency declared anywhere — confirmed and fixed.
3. **Dependency lock.** Added `requirements-lock.txt` via `uv pip compile pyproject.toml --extra
   v1 --extra dev` — 349 pinned lines. `pyproject.toml`'s open `>=` bounds remain the published
   package's compatibility range; the lock is for reproducible dev/CI installs.
   > **Superseded by Lot 9** (external plan; not this file's own Lot sequence): the `--extra v1
   > --extra dev` command above only ever covered dev/CI installs, but the Dockerfile installs
   > `[v1,langgraph,postgres,auth]` and never consumed this lock at all until Lot 9 wired it in.
   > The regenerate command is now `uv pip compile pyproject.toml --python-platform linux
   > --python-version 3.12 --extra v1 --extra dev --extra langgraph --extra postgres --extra auth
   > -o requirements-lock.txt` — see
   > [docs/guides/dependency-lock.md](../guides/dependency-lock.md) for the full, current,
   > maintained procedure. This entry is left otherwise unedited as the historical record of what
   > Lot 3 itself actually did.
4. **mypy `python_version` bug found and fixed.** `[tool.mypy] python_version = "3.11"` crashed
   immediately (`exit 2`) against `numpy`'s bundled type stubs, which use a `type` statement
   only valid under Python 3.12+ parsing — this is a real bug uncovered by actually running the
   configured toolchain for the first time, not a pre-existing known issue. Bumped to
   `python_version = "3.12"`, matching the actual dev environment and one of the two versions
   already claimed in `pyproject.toml` classifiers. Trade-off noted: this means mypy no longer
   verifies 3.11-specific compatibility; revisit if/when a real Python-version CI matrix is
   added (explicitly out of scope for this lot).
5. **mypy baseline captured.** `.claude/mypy-baseline.txt` created (mirrors the existing
   `.claude/layering-baseline.txt` accepted-violations pattern, but as a count ratchet rather
   than a line-by-line list — mypy's own line numbers/wording shift with unrelated refactors,
   so exact-diff would be noisy). **Baseline: 35 errors**, all pre-existing, none introduced by
   this lot. Full list at time of capture:
   - `retrieval/retrievers/bm25.py:33`, `vector.py:49` — stale/incorrect `type: ignore` comments
     masking real `attr-defined` errors against `object`-typed lazy-loaded clients
   - `app/container.py:39,43,47,51,59` — 5x `Returning Any from function declared to return X`
     (DI container factories)
   - `orchestration/engine.py:37,57` — missing generic type args, unused `type: ignore`
   - `ingestion/pipelines/default.py:26,30` — `object` has no attribute (`supports`/`parse`)
   - `generation/synthesizers/anthropic_gen.py:64`, `openai_gen.py:73` — same lazy-client
     `attr-defined` pattern as retrievers above
   - `adapters/embeddings/openai_embedder.py:36`, `adapters/vectorstores/qdrant_store.py`
     (6 errors) — lazy-client init typed as `None`, calls on it flagged; one missing return
     annotation
   - `retrieval/rerankers/cross_encoder.py:36` — same lazy-client pattern
   - `adapters/embeddings/hf_embedder.py:39` — `Returning Any`
   - `api/__init__.py:25,29,45` — missing generic type args for `dict`
   - `generation/citations/builder.py:39`, `security/detectors/adversarial.py:32` — unused
     `type: ignore`
   These cluster into two fixable patterns (lazy-loaded-client typing, missing generic args) —
   worth a dedicated cleanup pass, not fixed here since Lot 3's job is capturing the baseline,
   not zeroing it.
6. **`scripts/check.sh` `full` fixed and extended.** The mypy step had a logic bug
   (`grep -q ... && [[ ${PIPESTATUS[0]} -ne 0 ]]` checked `grep`'s exit status, not mypy's —
   effectively a permanent no-op that always printed "not blocking"). Replaced with a baseline
   count comparison against `.claude/mypy-baseline.txt`. Also added, per the lot's original
   scope: a compilation-check step (`python -m compileall`) and the layering audit
   (`scripts/check_layering.py --strict`), neither of which were wired into `check.sh` or CI
   before this lot despite both existing standalone.
7. **`.github/workflows/ci.yml` rewritten.**
   - `lint` job: ruff, compilation check, strict layering audit, and the baseline-ratcheted mypy
     check (was `|| true`, fully non-blocking).
   - `test-unit`, `test-contract`, `coverage`: install command fixed from
     `.[dev] || .` (silently falling back without `v1` extras) to `.[v1,dev]` explicitly.
   - New `build-and-smoke-test` job: builds a wheel, installs it into a throwaway venv with the
     `v1` extra, verifies `import modular_rag` and the `mrag version` console-script entry point
     both work from a clean install — none of this existed before.
   - Python version bumped 3.11 → 3.12 across all jobs, matching the environment actually
     validated in this lot and the mypy config fix in item 4. A 3.11 matrix entry is not added
     here (out of scope, noted below).
   - `.gitlab-ci.yml` deliberately left untouched — `CLAUDE.md` §08 already directs new CI work
     to GitHub Actions; duplicating this effort into the legacy pipeline was explicitly out of
     scope for this lot. Flagged for removal consideration at Lot 17.
8. **Two pre-existing lint violations fixed** (`eval/runners/benchmark.py`,
   `retrieval/retrievers/vector.py` import order; `agents/validator/validator.py` unnecessary
   generator → set comprehension) — never caught before because `ruff check --select
   E,F,I,N,W,UP,B,C4` (the `full`-check rule set) had never actually been run in a working
   environment until this lot.

## Verification evidence

- `python scripts/check_layering.py --strict` → passes, 0 violations.
- `python -m compileall -q src/modular_rag` → passes.
- `mypy src/modular_rag/ --no-error-summary` → 35 errors, matches baseline exactly.
- `pytest tests/unit/ tests/contract/ --cov=src/modular_rag` → **199 passed**, coverage report
  generated (65% overall; lowest-covered areas are `orchestration/` at 0% — untested — and
  `eval/runners/benchmark.py`, `eval/scorers/retrieval_metrics.py` — noted for Lot 4
  characterization work, not fixed here).
- `python -m build --wheel` → builds `modular_rag-0.0.1-py3-none-any.whl` cleanly.
- Wheel installed into a throwaway venv with `[v1]` extra → `import modular_rag` and
  `mrag version` both succeed (`modular-rag 0.0.1`).
- `./scripts/check.sh full` → all 6 steps pass end-to-end.
- `.claude/settings.json` re-validated as parseable JSON after Lot 2's edits (unrelated to this
  lot but checked as part of the same working session).

## Not in scope for this lot (explicitly deferred)

- Python 3.11 CI matrix entry — classifiers claim 3.11+3.12 support but only 3.12 is now
  exercised (3.11 wasn't exercised before either, since mypy's config crashed under it with the
  installed numpy stub version). Revisit alongside the mypy `python_version` trade-off in item 4.
- Fixing the 35 baselined mypy errors — captured, not zeroed. Budget reduction is a deliberate
  follow-up per the plan ("reduce the budget deliberately thereafter"), not this lot's job.
- `.gitlab-ci.yml` — untouched, flagged for Lot 17.
- Raising test coverage on `orchestration/` (0%) — Lot 4's characterization-test scope, not this
  lot's.

## Acceptance evidence (per `docs/refactoring-plan.md` §6, Lot 3 row)

"Fresh install and offline gates pass in local/CI parity; dependency and type baselines
recorded" — satisfied: fresh `.venv` install verified working end-to-end locally via
`check.sh full`; `requirements-lock.txt` and `.claude/mypy-baseline.txt` are the recorded
baselines; `.github/workflows/ci.yml` runs the same gates GitHub-side (unverified by an actual
GitHub Actions run as of this writing — first push/PR against this branch is the remaining
confirmation step).
