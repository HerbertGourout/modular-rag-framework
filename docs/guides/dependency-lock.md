# Reproducible dependency lock: update procedure

Lot 9 (an external plan; not this repository's own `docs/refactoring-plan.md` Lot sequence,
which is unrelated and already used through Lot 18 for different, completed work) made the
Docker build actually reproducible: `Dockerfile`'s runtime stage now installs the built wheel
constrained by `requirements-lock.txt` (`pip install -c requirements-lock.txt "wheel[...]"`)
instead of resolving every transitive dependency freely against whatever is newest on PyPI at
build time. This document is the controlled procedure for changing that lock — read it before
touching `requirements-lock.txt` or the extras either the Dockerfile or this file's own `uv pip
compile` invocation names.

## What the lock covers, and why it's wider than the image

`requirements-lock.txt` is generated for the **union** of `v1 + dev + langgraph + postgres +
auth` — not just the three non-`dev` extras (`v1,langgraph,postgres,auth`) the Dockerfile actually
installs. This is deliberate, not an oversight:

- The Dockerfile's `pip install -c requirements-lock.txt "wheel[v1,langgraph,postgres,auth]"`
  uses the lock as a **constraints file** — constraints only cap the version of a package pip has
  already decided to install for some other reason; they never force an install by themselves.
  Keeping `dev`'s packages (pytest, mypy, ruff, build, ...) pinned in the same lock costs nothing
  at image-build time and preserves the lock's original purpose from Lot 3 (reproducible
  local/CI dev-tooling installs), so there is no need for two separate lock files.
- `scripts/check_lock_sync.py` (below) checks that the lock is a **superset** of what the
  Dockerfile installs, not that the two match exactly — regenerating with a wider `--extra` set
  than the image needs is always safe; a **narrower** one is the actual failure mode this script
  catches.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) installed and on `PATH` (`uv --version`). This project does
  not otherwise depend on `uv` — it is a lock-generation tool only, never installed as part of
  any extra, and never required to install or run the framework itself.
- A clean `git status` before you start, so the regenerated lock's diff is easy to review in
  isolation from unrelated changes.

## Exact command

```bash
uv pip compile pyproject.toml \
  --python-platform linux \
  --python-version 3.12 \
  --generate-hashes \
  --extra v1 --extra dev --extra langgraph --extra postgres --extra auth \
  -o requirements-lock.txt
```

**`--generate-hashes`** (added after Codex review MEDIUM-002, integrity): each pinned line now
carries one or more `--hash=sha256:...` entries authenticating the exact bytes an index/mirror
must serve for that version — a version pin alone only constrains *which* release, not that the
bytes served under it are the ones actually published.

**This is not paired with hash *enforcement*, and every install command referencing this file
needs `--no-require-hashes` because of it.** pip enters hash-checking mode automatically the
instant it sees any requirement with a hash attached — not only when `--require-hashes` is passed
explicitly.

Confirmed directly, twice:
1. `pip install -c requirements-lock.txt -e ".[...]"` failed outright ("cannot be installed when
   requiring hashes, because there is no single file to hash"), because an editable/local source
   directory has no single artifact to hash.
2. After actually building this project's real wheel and running `pip install -c
   requirements-lock.txt <wheel>[...]` against it, pip still failed — this time demanding a hash
   for the *wheel itself*, which it cannot have. A freshly-built wheel is not byte-reproducible
   build to build, so pinning its hash the same way a downloaded PyPI package's hash is pinned
   isn't meaningful today. It would need the wheel build itself to be byte-for-byte deterministic
   first — a materially larger undertaking, tracked as an open follow-up, not silently dropped.

Both the Dockerfile's runtime-stage install and CI's `supply-chain` job now pass
`--no-require-hashes` (available from pip 26.2, matching the pin used), specifically to opt back
out of this automatic behavior while still using every version pin in the lock.

The hashes remain present and useful regardless: `scripts/check_lock_sync.py` strips them for its
own internal dry-run checks (same reason), but a hash-aware installer or a future, fully-enforced
install path can still verify against this same file at any time.

**`--python-platform linux --python-version 3.12` is not optional.** `uv pip compile` resolves
for whatever platform you tell it to target. Omit these flags and running the command on macOS
or Windows silently produces a lock missing Linux-only transitive packages the image actually
needs (confirmed directly while writing this: re-running the command without `--python-platform
linux` on a Windows machine dropped `uvloop`, a Linux-only transitive dependency of
`uvicorn[standard]`, entirely).

The Dockerfile always targets `python:3.12-slim` (Debian/Linux) regardless of which OS you run
this command from — the lock must match the *target*, not your workstation.

## Extras covered, and when to widen the list

Regenerate with **exactly** the `--extra` flags above unless one of these changed:

- A new extra was added to the Dockerfile's `pip install "${WHEEL_FILE}[...]"` line — add the
  matching `--extra NAME` here too, in the same change.
- A new extra was added to `pyproject.toml` that the Dockerfile does not install and never will
  (e.g. a future `v4`/`v5` once those are actually wired into code) — do **not** add it here
  speculatively; the lock only needs to cover what something real actually installs from it
  (the Dockerfile's extras, plus `dev` for local/CI tooling).

## After regenerating: review the diff

`uv pip compile` re-resolves against the live PyPI index every time it runs — two runs minutes
apart can legitimately produce different pinned versions as upstream packages publish new
releases (also confirmed directly while writing this document). A diff in `requirements-lock.txt`
is therefore expected on every regeneration, not itself a red flag. What to actually look for in
the diff:

- **New top-level entries with no `# via modular-rag (pyproject.toml)` comment tracing back to
  something you intentionally added to `pyproject.toml`** — an unexpected new *direct* dependency
  usually means a typo'd extra name or an accidental scope widening.
- **A package disappearing entirely** — check whether that's because you removed it from
  `pyproject.toml` on purpose, or because its own dependents changed how they declare it.
- **Version pins moving backward** — `uv pip compile` should never downgrade something you didn't
  touch; if it does, something about your local `uv` cache or index configuration is stale.

## Required validations after a lock change

Run, in order, and do not proceed past a failure:

1. `python scripts/check_lock_sync.py` — the deterministic gate (also run in CI's `lint` job).
   Checks:
   - Direct-dependency coverage (base `dependencies` and each Dockerfile extra).
   - Strict lock-line syntax (bare or `--generate-hashes`-annotated).
   - The Dockerfile/`.dockerignore` wiring.
   - The build-backend pin match between `pyproject.toml` and the Dockerfile's builder stage.
   - A real `pip install --dry-run --report` resolution proving every *transitive* package the
     exact Dockerfile extras need is present in the lock, not just the direct ones (Codex review
     HIGH-003 — a lock naming only `pydantic`/`uvicorn` and omitting every one of
     `uvicorn[standard]`'s own transitives passed the direct-only version of this check).

   That last check is **only authoritative when run on Linux** (pip evaluates dependency markers
   against the host interpreter, not an overridable target). It self-detects and prints a clear
   skip message on other platforms rather than reporting Windows-only conditional packages as
   false gaps, or silently claiming coverage it did not verify. Treat a local, non-Linux run's
   `OK` as provisional; CI's `lint` job (`ubuntu-latest`) is what actually proves this.

   **On Linux, by contrast, this sub-check fails closed**: a timeout, a resolver conflict, or any
   other inability to complete the resolution there is itself a hard failure (Codex review
   HIGH-003, round 2 — the first version treated every one of those the same as the legitimate
   non-Linux skip, so a CI run where pip couldn't even produce an answer still printed `OK` and
   exited 0).
2. `python scripts/check_dockerfile_permissions.py` — unaffected by a lock-only change, but cheap
   to confirm nothing about the Dockerfile itself regressed in the same pass.
3. `pip-audit -r requirements-lock.txt` (needs `pip-audit` installed — `pip install
   -e ".[supply-chain]"`; no shipped-extras install needed for this specific command, since `-r`
   audits the lock file's own pinned versions directly rather than a live environment, matching
   CI's own `supply-chain` job below — this only resolves correctly on Linux, since the lock
   contains Linux-only transitives like `uvloop`/CUDA packages; a Windows/macOS run will report
   spurious platform errors, not real findings) — a lock change is exactly the kind of edit that
   can newly introduce a vulnerable transitive version.
4. `python scripts/check_licenses.py --python <path-to-a-venv-containing-only-the-shipped-extras>`
   — the licence gate; a new transitive dependency can carry a licence not yet in
   `.claude/license-baseline.txt`. Point `--python` at a dedicated venv installed with `pip install
   --no-require-hashes -c requirements-lock.txt -e ".[v1,langgraph,postgres,auth]"` (no
   `supply-chain` extra) so the scan reflects the shipped closure only, not a tooling-contaminated
   one — see "supply-chain CI job" below for why.
5. `python -m cyclonedx_py environment --output-format json -o sbom.json
   <path-to-that-same-shipped-only-venv-python>` — regenerate the SBOM evidence so it actually
   describes what the new lock resolves for the shipped image specifically.
6. `pytest tests/unit tests/contract` and `python scripts/check_layering.py` — a lock change
   should never affect these, but confirming that is cheap and catches an unrelated regression
   before it gets attributed to the lock change later.
7. **Image validation, only if Docker is actually available**: `docker build -t modular-rag:local
   .` then `docker run -d -p 8000:8000 modular-rag:local` and poll `GET /health` — this is the
   step CI's `container-build` job performs on every push; a local Docker daemon can run it
   sooner. Never claim this step passed without actually running it — if no Docker daemon is
   available, say so explicitly rather than asserting the image builds.

## `supply-chain` CI job now scans the shipped closure, not a wider one

CI's `supply-chain` job builds a **dedicated venv** (`shipped-venv`) containing *only* what the
Docker image itself installs — `pip install --no-require-hashes -c requirements-lock.txt -e
".[v1,langgraph,postgres,auth]"`, no `supply-chain` extra in that same environment — then installs
`pip-audit`/`pip-licenses`/`cyclonedx-bom` separately, unconstrained, into the job's main
environment. Each tool is then pointed at the shipped closure specifically, not the combined
environment:

- `pip-audit -r requirements-lock.txt` audits the lock file's own pins directly (no venv needed).
- `python scripts/check_licenses.py --python shipped-venv/bin/python` (the script's own `--python`
  flag, added in the same round, passes through to `piplicenses --python`).
- `python -m cyclonedx_py environment ... shipped-venv/bin/python` (the `environment` subcommand's
  own positional `<python>` argument).

Before Codex review MEDIUM-001's first round, this job ran `pip install -e ".[all,supply-chain]"`
— unconstrained by the lock at all, and `all` includes `v4`/`v5`, which the image never installs —
so a vulnerable *locked* version could pass `pip-audit` by having it resolve a newer, fixed version
instead. The first correction (constraining a single combined environment with `-c
requirements-lock.txt -e ".[v1,langgraph,postgres,auth,supply-chain]"`) closed the version-mismatch
gap but left `pip-licenses`/the SBOM inventorying that same combined, tooling-contaminated
environment — still not an exact match for the shipped image's own closure (Codex review
MEDIUM-001, round 2). The dedicated-venv split above is what actually closes that. Full detail on
`--python` support in `check_licenses.py`'s own docstring/`--help`.

## Image vulnerability scan: Grype, not Trivy — why

CI's `container-build` job now also runs `anchore/scan-action` (wraps
[Grype](https://github.com/anchore/grype)) against the just-built `modular-rag:ci` image, pinned
by full commit SHA (not a mutable tag), `severity-cutoff: high` (fails the build on any `HIGH` or
`CRITICAL` finding; `MEDIUM`/`LOW` are reported but non-blocking), `fail-build: true`.

The more commonly-templated default for this exact job shape is `aquasecurity/trivy-action`.
It was deliberately not chosen here: live research while writing this lot surfaced that
`trivy-action` suffered a real, documented supply-chain compromise in March 2026 — a threat actor
force-pushed 76 of its 77 release tags to malicious commits that stole CI/CD secrets
(GitHub Security Advisory
[GHSA-69fq-xp46-6x23](https://github.com/advisories/GHSA-69fq-xp46-6x23), tracked as
CVE-2026-33634; only the `v0.35.0` tag was confirmed to have stayed intact). Picking a tool with
that specific, recent, well-documented tag-hijacking history as the default for a lot whose entire
point is hardening supply-chain trust would have been the wrong call even with careful SHA-pinning
on top of it. The same research pass turned up no comparable incident for `anchore/scan-action`.
This is a documented, deliberate choice — not an oversight if a future reviewer expects Trivy by
default.

**Refreshing the pin**: resolve the new commit SHA for a release tag via GitHub's API before
changing the pin —
`https://api.github.com/repos/anchore/scan-action/git/refs/tags/vX.Y.Z` (or the `/tags` list
endpoint) — never hand-type or guess a SHA. Update the version comment (`# vX.Y.Z`) alongside it
so the two never drift apart silently.

**Findings visibility**: the gating scan step uses `output-format: table` directly (not `sarif`) so
HIGH/CRITICAL findings that fail the build are printed in the job log itself, not only to a file. A
second, non-gating step (`fail-build: false`, `if: always()`) re-runs the same scan purely so the
full table is visible even if something upstream of it changes; this is currently redundant with
the first step's own table output but kept for the case the gating step's format ever changes back.
A SARIF report is deliberately **not** uploaded to the repository's code-scanning tab
(`github/codeql-action/upload-sarif`, previously used here): GitHub Advanced Security — which Code
scanning is part of — is only available for private repos owned by an Organization on a qualifying
plan, never for a private, personal-account repo, confirmed directly from this repo's own
Settings > Security > Code security page ("Advanced Security is only available for
Organizations"). That upload step always failed here with "Code scanning is not enabled for this
repository" and was removed 2026-09-03 rather than kept as permanently-dead CI weight.

**Won't-fix policy** (`.grype.yaml`, repo root, auto-detected by `anchore/scan-action` — no
`config` input is set): `severity-cutoff: high` would otherwise be permanently unsatisfiable, since
every current `python:3.12-slim` (Debian trixie) build carries HIGH/CRITICAL findings on system
packages (`perl-base`, `libc6`/`libc-bin`, `libncursesw6`/`libtinfo6`/`ncurses-*`, `libsqlite3-0`,
`libacl1`, `gzip`, ...) that Debian's own security team has explicitly declined to backport a fix
for. `.grype.yaml`'s `ignore: [{fix-state: wont-fix}]` rule ignores by Grype's own first-class
`fix-state` category (see `grype/vulnerability/fix.go`'s `FixStateWontFix`), not a hand-listed CVE
ID list — a new won't-fix CVE on any of these same packages would otherwise fail the build again
with zero actual change on this project's side. Findings are still fully visible in the readable
table above; only the build-failing behavior changes. Three additional, individually-listed
entries (`CVE-2026-4224`, `CVE-2026-7210`, `CVE-2026-3644` on `python` itself) are a genuinely
different case — a real fix exists, just not on the pinned 3.12.x interpreter line — accepted as an
explicit, separate risk until this project moves its minimum supported Python version. A fifth
entry (`CVE-2026-85091` on `zlib1g`, accepted 2026-09-06) is different again: `fix-state: not-fixed`,
not `wont-fix` — a fresh CVE with no patch anywhere yet (neither Debian nor upstream zlib), narrow
attack surface (`gzprintf`/`gzvprintf` misuse this project's own code never exercises), tracked to
be removed once a fix ships rather than folded into the blanket won't-fix rule. All entries are
dated and reviewed; see the file's own header comment for the acceptance record.

## Base image: digest-pinned, refresh procedure

`Dockerfile`'s `FROM python:3.12-slim@sha256:...` is pinned to a specific digest in **both**
stages (Codex review HIGH-001 — the Python dependency lock alone cannot repair an interpreter,
system libraries, or bundled tools that a floating tag silently moved between two builds of the
same commit). The current digest was resolved from Docker Hub's own v2 API
(`https://hub.docker.com/v2/repositories/library/python/tags/3.12-slim`, the `digest` field),
cross-checked against the registry's own v2 manifest API (`docker-content-digest` header) returning
the identical value, on 2026-09-03 — refreshed from the prior 2026-08-19 pin to pick up Debian's
openssl/libssl3t64 security update after CI's Grype gate flagged the old digest — not guessed. A
human with real Docker access should still cross-verify before treating it as production-final:

```bash
docker pull python:3.12-slim
docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
```

**Refreshing the pin** (Debian/Python patch releases move the floating tag forward; a pinned
digest silently stops receiving those security patches until someone deliberately re-pins it —
put this on a recurring calendar reminder, not only "when something breaks"):

1. Query `https://hub.docker.com/v2/repositories/library/python/tags/3.12-slim` for the current
   `digest` field (or run the `docker pull`/`docker inspect` pair above against a real daemon —
   preferred when available, since it is a direct, first-party read rather than a third-party API).
2. Update `python:3.12-slim@sha256:...` in **both** `Dockerfile` stages together — a
   builder/runtime split on different digests defeats the point.
3. Rerun the full validation sequence below, including an actual `docker build` if at all possible.

## Build backend (Hatchling and the whole build toolchain): pinned, refresh procedure

`pyproject.toml`'s `[build-system].requires` pins `"hatchling==1.32.0"`, and the Dockerfile's
builder stage installs `pip`, `build`, and that exact Hatchling version, constrained by
`requirements-lock.txt` (`-c /tmp/requirements-lock.txt`, `--no-require-hashes` for the same
automatic-hash-checking-mode reason documented above), building with `python -m build --wheel
--no-isolation` (Codex review HIGH-002).

**Why the lock, not a hand-picked transitive list**: the first version of this fix pinned
Hatchling's transitives by name individually (`packaging`, `pathspec`, `pluggy`, `tomlkit`,
`trove-classifiers`), but missed that `build==1.5.0` *itself* unconditionally requires
`pyproject_hooks` — confirmed via `importlib.metadata.requires("build")` — which was never in that
hand-picked list and so still resolved freely from the live index (Codex review HIGH-002, round
2). `requirements-lock.txt` already resolves `build`'s complete transitive closure exactly once,
correctly, via the `dev` extra (`build>=1.2` is a `dev` dependency) — constraining the builder
install against it closes this without hand-maintaining a second, parallel, easily-incomplete
transitive list. Only `tomlkit` and `trove-classifiers` need an explicit version on the command
line: they are Hatchling-exclusive and the lock has no other reason to resolve them (Hatchling
itself is not a `[project]` dependency, so `uv pip compile` never pulls it or its own transitives
in). Do **not** also hand-pin `packaging`/`pathspec`/`pluggy` explicitly alongside `-c
requirements-lock.txt` — a separately-resolved version of one of those conflicted outright with
the lock's own pin the first time this was tried (`ResolutionImpossible`, reproduced directly);
let the lock's constraint govern them.

**Refreshing the Hatchling-exclusive pins**: resolve Hatchling's current version and transitives
the same way the main lock is generated —

```bash
echo hatchling > /tmp/hatchling-req.txt
uv pip compile /tmp/hatchling-req.txt --python-platform linux --python-version 3.12 -o -
```

— then update `pyproject.toml`'s `requires` entry and the Dockerfile builder stage's explicit
`hatchling==`/`tomlkit==`/`trove-classifiers==` pins together (`scripts/check_lock_sync.py`'s
build-backend check fails if the Hatchling version in the two diverge). Cross-check the output
against the current `requirements-lock.txt` for any of the other resolved names (`packaging`,
`pathspec`, `pluggy`) — if Hatchling's own required version range for one of them stops overlapping
with what the main lock pins, that is a real conflict to resolve deliberately (e.g. by bumping the
main lock), not by re-introducing a separate explicit pin here.

## Review rules before accepting a lock change

- A lock-only PR (no `pyproject.toml` change) should show only version-number diffs, never a
  package appearing or disappearing — if one does, something upstream restructured its own
  dependency tree; read why before merging.
- A PR that also touches `pyproject.toml`'s dependencies must regenerate the lock in the *same*
  commit — `scripts/check_lock_sync.py` blocks this in CI, but review it directly too: the
  diff should show the new/removed package appearing/disappearing from the lock as a direct
  consequence.
- Never hand-edit `requirements-lock.txt` — always regenerate via the exact command above so the
  header comment (which the lock itself, and nothing else, is the source of truth for) stays
  accurate.
- A version bump that changes a package's **major** version warrants an explicit look at that
  package's own changelog for breaking changes, independent of whether CI stays green — CI
  proves the change didn't break anything CI covers, not that it's safe.
