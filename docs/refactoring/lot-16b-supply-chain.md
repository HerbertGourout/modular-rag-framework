# Lot 16b — Supply Chain: SBOM, Vulnerability/Licence Gates, Version Source, Container Build

**Date:** 2026-08-05
**Status:** COMPLETE (engineering scope) — two findings escalated for an explicit owner decision, see "Escalated, not decided" below

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Immutable wheel/container builds, SBOM, vulnerability and licence gates (including the 56
> research PDFs' redistribution rights), and one authoritative version source. Independent of
> 16a — different files, can run in parallel with a second owner.

## What was built

| File | Purpose |
|---|---|
| `src/modular_rag/__init__.py` | `__version__` now reads `importlib.metadata.version("modular-rag")` instead of a hardcoded `"0.0.1"` literal — `pyproject.toml`'s `[project].version` is the one remaining authoritative source; this reads it back so the two can never drift. Falls back to `"0.0.0+unknown"` only if imported from source without ever running `pip install [-e] .`. |
| `src/modular_rag/api/__init__.py` | `FastAPI(version="0.0.1")` literal replaced with `version=__version__`. |
| `scripts/check_licenses.py` (new) | Dependency licence gate. Classifies every installed package's declared licence against a permissive allowlist (MIT/BSD/Apache/ISC/PSF/MPL-2.0/Unlicense/CC0/Zlib/0BSD/Boost); anything not permissive must be named in `.claude/license-baseline.txt` with a recorded reason or the gate fails. Mirrors the `.claude/mypy-baseline.txt`/`.claude/layering-baseline.txt` accepted-exception ratchet pattern already established in this codebase, rather than inventing a new mechanism. |
| `.claude/license-baseline.txt` (new) | Two currently-accepted exceptions, each with a recorded reason — see "Findings" below. |
| `pyproject.toml` | New `supply-chain` optional-dependency group (`pip-audit`, `pip-licenses`, `cyclonedx-bom`) — audit tooling, not needed to run the framework, so deliberately not added to the `all` extra (same "opt-in infra" precedent as Postgres/pyjwt in earlier lots). |
| `.github/workflows/ci.yml` | New `supply-chain` job: installs `.[all,supply-chain]`, runs `pip-audit --skip-editable` (vulnerability gate), `scripts/check_licenses.py` (licence gate), and generates + uploads a CycloneDX SBOM as a build artifact. New `container-build` job: builds the `Dockerfile` and smoke-tests it (`docker run` + poll `/health`) — this is where the Dockerfile actually gets built and executed, since this sandboxed environment has no `docker` binary to verify it locally. |
| `Dockerfile` (new) | Multi-stage immutable build: a `builder` stage runs `python -m build --wheel` from source (same as CI's existing `build-and-smoke-test` job); the `runtime` stage installs only the built wheel (`[v1]` extra) into a slim image running as a non-root user — never the source tree, dev tooling, or `.claude/research-papers/`. |
| `.dockerignore` (new) | Keeps the build context free of `.git/`, `.venv/`, `.claude/` (128MB of PDFs in particular), `docs/`, `tests/`, etc. — `README.md` is explicitly re-included (`!README.md`) since `pyproject.toml`'s `readme` field needs it present for the wheel build to succeed. |
| `docker/server.py` (new) | The one-line `create_app()` wrapper `docs/api/rest.md` already told every deployer to write themselves, made configurable via `MRAG_MANIFEST_PATH` (default: the one CI-validated runnable preset, `manifests/presets/local-hybrid-rag.yaml`) instead of hardcoding a path into the image. |

## Findings

### No known vulnerabilities

`pip-audit` (real scan against the fully-installed `[all,supply-chain]` environment, 209 packages)
reports zero known vulnerabilities as of 2026-08-05. `--skip-editable` excludes this project's own
editable install (not published to PyPI, so unauditable by definition) without silencing genuine
findings on any real dependency.

### Licence gate: 209 packages, 2 accepted exceptions, 0 new violations

`scripts/check_licenses.py` passes with exactly the two pre-existing exceptions recorded in
`.claude/license-baseline.txt`:

| Package | Licence | Where it's used | Risk |
|---|---|---|---|
| `pymupdf` (`fitz`) | AGPL-3.0 / Artifex Commercial (dual) | PDF parsing, `v1`/`v5` extras (`.claude/.instructions.md` §4 lists `fitz` as a lazy-imported heavy dependency) | **Material.** AGPL's network-copyleft clause is a real constraint for any commercial/enterprise deployment of this framework as a service. |
| `chardet` | LGPLv2+ | Transitive (charset detection) | Low. LGPL explicitly permits ordinary dependency use without imposing its terms on the depending project, unlike GPL/AGPL. |

## Escalated, not decided

Two findings from this lot are legal/business-risk calls, not engineering ones — recorded here
rather than resolved unilaterally, per this programme's own decision-authority discipline
(`docs/refactoring/lot-0-baseline.md` §2: sole decision authority is Herbert Gourout; an agent
does not make binding legal-risk calls on their behalf):

1. **`pymupdf`'s AGPL/Artifex dual licence** (above). Three real options exist — accept the AGPL
   network-copyleft obligation for any deployment that runs this framework as a service, obtain
   an Artifex commercial licence, or replace `fitz` with a permissively-licensed PDF library
   (`pypdf`, `pdfplumber`) — each with different functional/cost trade-offs this lot does not
   evaluate. `.claude/license-baseline.txt` records the dependency as a currently-accepted risk
   pending that decision, not a resolved one.
2. **The 56 research PDFs' redistribution rights** (`.claude/research-papers/`, confirmed via
   `git ls-files` to be **fully tracked in git history**, ~128MB). All are arXiv preprints
   (filenames are arXiv IDs), but arXiv's default submission licence — "arXiv.org perpetual,
   non-exclusive licence to distribute" — does **not** itself grant third parties redistribution
   rights; many authors additionally attach CC-BY/CC-BY-SA/CC-BY-NC-*/CC0, but that varies
   per paper and isn't encoded in the filename or captured anywhere in this repository today.
   Confirming actual redistribution rights would require checking each paper's arXiv licence
   field individually (56 lookups) — not attempted in this lot. This repository's remote
   (`github.com/HerbertGourout/modular-rag-framework`) may be public; distributing 56 papers'
   worth of possibly-non-redistributable copyrighted PDFs via git history is a real risk this
   lot surfaces but does not resolve. `.dockerignore` already excludes `.claude/` from the
   *container image*, which limits exposure through that one channel, but does nothing about
   git history itself.

Both are flagged to Herbert Gourout directly (outside this document) for a decision; this lot's
engineering work (the gate mechanism itself, SBOM, version source, container build) is complete
independent of how those two calls land.

## Deliberately out of scope, recorded honestly

- The Dockerfile is **unbuilt and unverified in this sandboxed environment** — no `docker` binary
  is available here. The new `container-build` CI job (`docker build` + a real `docker run` +
  `/health` poll) is where this actually gets executed and proven, on the next push. This is the
  same "verifiable fakes / defer to real infra" pattern used for PostgreSQL and Keycloak in
  earlier lots, applied to a case where there's no meaningful local fake for "does this image
  build and start" — only a real Docker daemon can answer that.
- No container registry push, tagging strategy, or rollback procedure — that is Lot 16c's
  "deployment, backup, restore, and rollback runbooks," which this lot's own plan text says
  depends on 16b being done first (image exists) before 16c can write the runbook that uses it.
- `supply-chain` is not part of `scripts/check.sh`'s local `quick`/`full` tiers — it reflects
  installed-environment state (needs `pip-audit`/`pip-licenses`/`cyclonedx-bom` installed and
  live PyPI advisory-DB network access) rather than source, so it lives in CI only, matching how
  `integration`/`e2e` are already kept out of `full` for the same category of reason.

## Verification

`./scripts/check.sh full` — all 7 steps pass (mypy baseline unaffected, 31/31; 465 unit + 82
contract tests unaffected — this lot touched no test-covered runtime behavior, only version
sourcing and new supply-chain/container tooling).

Manually verified in this environment (not part of `check.sh`, since these tools aren't part of
`dev`/`v1`):
- `python scripts/check_licenses.py` — passes, 209 packages, 2 accepted exceptions (`[all,supply-chain]` installed).
- `pip-audit --skip-editable` — 0 known vulnerabilities.
- `python -m cyclonedx_py environment --output-format json` — valid CycloneDX 1.6 SBOM, 214 components.
- `python -c "import modular_rag; print(modular_rag.__version__)"` — prints `0.0.1`, read from installed metadata, not the old hardcoded literal.

## Tracker updates

- Header status block: Lot 16b → COMPLETE (engineering scope), two findings escalated.
- Gap matrix: "Versioning" row resolved.
- Decision log + change history: new Lot 16b entry, including the two escalated findings.
