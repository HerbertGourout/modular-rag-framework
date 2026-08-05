# Immutable container build (Lot 16b, docs/refactoring-plan.md — "immutable
# wheel/container builds"). Two stages: the builder produces a wheel from
# source exactly the way CI's build-and-smoke-test job does
# (.github/workflows/ci.yml); the runtime image installs only that wheel
# (plus the v1 extra — the same one docs/guides/validation.md and this
# repo's own CI smoke test use), never the source tree, dev tooling, or the
# 128MB .claude/research-papers/ corpus (excluded via .dockerignore). This
# is the "how it's built" half of Lot 16c's deployment runbook — 16c writes
# the actual build/run/push/rollback procedure against this file, per
# docs/refactoring-plan.md's own stated Lot 16b -> 16c dependency.

FROM python:3.12-slim AS builder
WORKDIR /src
RUN pip install --no-cache-dir --upgrade pip build
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
RUN python -m build --wheel

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 mrag
WORKDIR /app
COPY --from=builder /src/dist/*.whl /tmp/
RUN WHEEL_FILE=$(ls /tmp/*.whl) && \
    pip install --no-cache-dir "${WHEEL_FILE}[v1]" && \
    rm -rf /tmp/*.whl
COPY manifests/ manifests/
COPY docker/server.py server.py
USER mrag
EXPOSE 8000
# MRAG_MANIFEST_PATH selects the pipeline manifest (default: the one runnable
# preset validated in CI, manifests/presets/local-hybrid-rag.yaml — see
# manifests/README.md for why the other four are blueprint-only). Any
# secrets the manifest's ${VAR}/secret:// references need (Lot 9,
# app/config_resolution.py) must be injected as environment variables at
# `docker run`/orchestrator level, never baked into the image.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
