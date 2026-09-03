# Immutable container build (Lot 16b, docs/refactoring-plan.md — "immutable
# wheel/container builds"; reproducibility hardened in Lot 9, an external
# plan not to be confused with docs/refactoring-plan.md's own, unrelated Lot
# sequence — see docs/guides/dependency-lock.md). Two stages: the builder
# produces a wheel from source exactly the way CI's build-and-smoke-test job
# does (.github/workflows/ci.yml); the runtime image installs only that
# wheel, constrained by requirements-lock.txt (below) so every transitive
# dependency resolves to the exact version two builds of the same commit
# already agreed on, never the source tree, dev tooling, or the 128MB
# .claude/research-papers/ corpus (excluded via .dockerignore). This is the
# "how it's built" half of Lot 16c's deployment runbook — 16c writes the
# actual build/run/push/rollback procedure against this file, per
# docs/refactoring-plan.md's own stated Lot 16b -> 16c dependency.
#
# Base image pinned by digest (Lot 9, Codex review HIGH-001), not the
# floating `python:3.12-slim` tag -- a moving tag can change the interpreter
# patch version, system libraries, and bundled tools between two builds of
# the same commit, which the Python dependency lock alone cannot repair.
# Digest resolved from Docker Hub's own v2 API (repositories/library/python/
# tags/3.12-slim) on 2026-09-03 -- cross-checked against the registry's own
# v2 manifest API (`docker-content-digest` header on
# registry-1.docker.io/v2/library/python/manifests/3.12-slim), both
# returning the identical value; refreshed from the prior 2026-08-19 pin to
# pick up Debian's openssl/libssl3t64 security update (CI's Grype gate
# flagged the old digest's openssl as HIGH/CRITICAL -- see
# docs/guides/dependency-lock.md's Grype section). A human with real Docker
# access should still cross-verify with `docker pull python:3.12-slim &&
# docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim`
# before this is treated as production-final, since this sandboxed
# environment has no `docker` binary to perform that check itself (verified
# directly). Refresh procedure and the exact command are in
# docs/guides/dependency-lock.md; both stages below MUST be updated
# together -- a builder/runtime split on different base digests defeats the
# point.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS builder
WORKDIR /src
# Pinned, not "--upgrade" to whatever's latest at build time (Lot 9) --
# matches this repo's own dev environment (pip) and requirements-lock.txt's
# own "build" pin, so the wheel-building toolchain itself is as reproducible
# as the dependencies it resolves. Hatchling (the build BACKEND declared in
# pyproject.toml's [build-system]) is pinned here too, with its own resolved
# transitives (Codex review HIGH-002): `python -m build`'s default isolated
# environment would otherwise install whatever the newest Hatchling happened
# to be at build time, silently varying the built wheel's own metadata/layout
# between two builds of the same commit -- pinning runtime dependencies alone
# cannot repair a wheel that was already built with moving inputs.
# --no-isolation uses this same environment instead of building a fresh one.
#
# `-c requirements-lock.txt` (Codex review HIGH-002, round 2): `build`
# itself unconditionally requires `pyproject_hooks`, which the earlier
# explicit-pin list omitted entirely -- confirmed via `importlib.metadata.
# requires("build")` -- so it resolved freely from the live index despite
# every *named* package here being pinned. The lock already resolves that
# (and every other `build`/`dev`-extra transitive) exactly once via the
# `dev` extra, so constraining against it here closes the gap without
# hand-maintaining a second, parallel transitive list. Hatchling's own
# transitives that happen to already appear in the lock (`packaging`,
# `pathspec`, `pluggy` -- pulled in by unrelated packages like `build`/mypy)
# are deliberately NOT re-pinned to a separately-resolved version here: an
# earlier draft of this fix pinned `packaging==26.3` explicitly and it
# conflicted outright with the lock's own `packaging==26.2` pin
# (`ResolutionImpossible`, reproduced directly) -- only `tomlkit` and
# `trove-classifiers`, which the lock has no other reason to pin, need an
# explicit version here. `--no-require-hashes`: same automatic
# hash-checking-mode trigger as the runtime install below, for the same
# reason (the lock now carries hashes). Not a BuildKit `--mount=type=bind`
# (would need a `# syntax=` pragma this Dockerfile doesn't declare, and
# couldn't be verified without a real Docker daemon) -- a plain `COPY`,
# same proven pattern the runtime stage below already uses.
COPY requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir pip==26.2 && \
    pip install --no-cache-dir --no-require-hashes -c /tmp/requirements-lock.txt \
    pip==26.2 build==1.6.0 \
    hatchling==1.32.0 tomlkit==0.15.1 trove-classifiers==2026.6.1.19 && \
    rm -f /tmp/requirements-lock.txt
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN python -m build --wheel --no-isolation

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime
RUN useradd --create-home --uid 1000 mrag && \
    mkdir -p /home/mrag/.cache/huggingface && \
    chown -R mrag:mrag /home/mrag/.cache
# HF_HOME pins sentence-transformers/transformers' own cache location to
# exactly the directory just created and chowned above (and that
# compose.yaml's hf_cache named volume mounts onto) -- without this, a
# library-version bump that changes its default cache path would silently
# stop matching either the pre-created ownership or the volume mount target
# (Lot 9; see scripts/check_dockerfile_permissions.py, which checks the
# mkdir+chown but cannot see whether the library actually honors that path
# without HF_HOME pinning it explicitly).
ENV HF_HOME=/home/mrag/.cache/huggingface
WORKDIR /app
COPY --from=builder /src/dist/*.whl /tmp/
COPY requirements-lock.txt /tmp/requirements-lock.txt
# Lot 9: -c (constraints) pins every transitive dependency's version to
# requirements-lock.txt's exact resolution instead of letting pip resolve
# freely against whatever is newest on PyPI at build time -- constraints cap
# versions without themselves requesting installation, so the wheel's own
# [v1,langgraph,postgres,auth] extras still decide *what* gets installed;
# the lock only decides *which exact version* of each. scripts/check_lock_sync.py
# is the CI gate that fails if these extras ever diverge from what the lock
# actually covers, AND that every transitive dependency the exact extras
# below actually need is present in the lock (Codex review HIGH-003 --
# not just the direct ones pyproject.toml names).
#
# The lock now also carries --hash= entries (Codex review MEDIUM-002,
# integrity, not just version pinning). pip enters hash-checking mode
# AUTOMATICALLY the instant any requirement it sees has a hash -- confirmed
# directly by actually building this project's real wheel and running this
# exact command: it failed demanding a --hash for the wheel file itself too
# ("hashes are required in --require-hashes mode... it turns on
# automatically when any package has a hash"), since a freshly-built wheel
# is not byte-reproducible build to build and so cannot be hash-pinned the
# same way a downloaded PyPI package can. --no-require-hashes (pip>=26.2,
# matching the pin above) opts back out of that automatic behavior while
# still using every version pin in the lock -- full hash *enforcement* for
# the wheel itself remains a real, open follow-up (see
# docs/guides/dependency-lock.md), not silently dropped, but this specific
# combination could not work as originally written.
#
# --extra-index-url: requirements-lock.txt pins a `+cpu`-tagged torch build
# (a CPU-only wheel, pulled in transitively via sentence-transformers under
# the `v1` extra) that only exists on PyTorch's own package index, never on
# PyPI -- every CI job's own `pip install -e .` already passes this same
# flag (.github/workflows/ci.yml); this runtime install line was the one
# place that didn't, so it failed here with "no matching distribution" for
# torch even though the exact same lock resolves fine everywhere else.
RUN WHEEL_FILE=$(ls /tmp/*.whl) && \
    pip install --no-cache-dir pip==26.2 && \
    pip install --no-cache-dir --no-require-hashes --extra-index-url https://download.pytorch.org/whl/cpu -c /tmp/requirements-lock.txt "${WHEEL_FILE}[v1,langgraph,postgres,auth]" && \
    rm -rf /tmp/*.whl /tmp/requirements-lock.txt
COPY manifests/ manifests/
COPY docker/server.py server.py
COPY docker/local-hybrid-rag.yaml docker/local-hybrid-rag.yaml
USER mrag
EXPOSE 8000
# MRAG_MANIFEST_PATH selects the pipeline manifest (default: the one runnable
# preset validated in CI, manifests/presets/local-hybrid-rag.yaml). The image
# includes the extras required by every runnable preset; blueprints remain non-runnable. Any
# secrets the manifest's ${VAR}/secret:// references need (Lot 9,
# app/config_resolution.py) must be injected as environment variables at
# `docker run`/orchestrator level, never baked into the image.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
