"""Automated smoke test for compose.yaml — "Lot 8: Compose et configuration
locale" (an external plan's own numbering; unrelated to this repo's own
docs/refactoring-plan.md Lot sequence, already used up to Lot 18 for
different, completed work — do not conflate the two).

Brings up the full local Docker Compose stack (API + Qdrant + PostgreSQL,
with the one-shot `migrate` service run to completion first) and proves it
actually *works*, not just that containers started:

- `GET /health` returns 200 quickly, with zero `.env` configuration.
- `GET /ready`'s `audit_sink` (PostgreSQL) role reports healthy immediately
  — proving the `migrate` service's `mrag db migrate` actually ran before
  `api` started (ADR-0011) — with zero `.env` configuration (no LLM key
  needed). The `indexer` (Qdrant) role is checked twice: present (but not
  necessarily healthy — see the ingestion bullet below) before ingestion,
  then required healthy afterward.
- `mrag ingest` against the running stack succeeds (sentence-transformers +
  Qdrant only, no LLM call) — run against a *fresh* Qdrant volume, whose
  `documents` collection does not exist until this step creates it, so the
  `indexer` readiness role is only required healthy *after* ingestion, not
  before (Codex review HIGH-001: `QdrantStore.check_health()` correctly,
  honestly reports a missing collection as unhealthy per ADR-0010 — that is
  not a bug to route around by skipping the pre-ingest state entirely, and
  requiring it healthy *before* ingestion had ever run made this script fail
  deterministically on the exact clean-start scenario it exists to prove).
  The ingestion fixture itself (`examples/simple_qa/docs`) is not part of
  the runtime image (`.dockerignore` excludes `examples/`) — compose.yaml's
  `api` service mounts it read-only for exactly this command (Codex review
  HIGH-002).
- The `generator` role, `/ready`'s aggregate status, and `mrag ask` are
  gated behind a real `OPENAI_API_KEY` actually being set: `/ready` can
  never report a fully "healthy" aggregate status without one (ADR-0010's
  `generator` is a critical role by design — see `orchestration/container.py`'s
  `_CRITICAL_ROLES`), and that is correct, intended behavior, not something
  this script tries to route around. Missing the key *skips* those specific
  assertions with a clear message by default; `--require-llm` turns that
  skip into a hard failure instead, for a CI job that has a real key
  configured as a secret.

Written but **not executed here**: no `docker`/`docker compose` binary is
available in this sandboxed development environment (verified directly —
`which docker` fails). This is the same "written correctly, not yet
proven" honesty already established throughout this codebase's own
integration tests (e.g. `tests/integration/test_postgres_lifecycle_ledger.py`'s
own docstring) — the first real run, by a human or a future CI job with
Docker available, is this script's actual verification.

Usage:
    python scripts/smoke_test_compose.py
    python scripts/smoke_test_compose.py --require-llm   # fail, don't skip,
                                                           # if OPENAI_API_KEY unset
    python scripts/smoke_test_compose.py --keep-up        # leave the stack
                                                           # running on success

Exit codes: 0 = pass; 1 = an assertion failed; 2 = a precondition failed
(no `docker`/`docker compose`, or --require-llm without a key).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
API_URL = "http://localhost:8000"
HEALTH_POLL_INTERVAL = 2.0
HEALTH_POLL_DEADLINE = 120.0
# OpenAIGenerator/AnthropicGenerator's own _HEALTH_CHECK_CACHE_SECONDS is
# 30.0 (generation/synthesizers/openai_gen.py) -- re-probing /ready sooner
# than that would just re-read the same cached generator-health result,
# proving nothing new about whether a transient startup delay has passed.
READY_RECHECK_DELAY = 31.0


def _dotenv_value(key: str) -> str | None:
    """Best-effort read of `key` from the repo-root `.env` file, mirroring
    what Docker Compose itself resolves for `${VAR}` interpolation into the
    `api` container's environment. `os.environ` alone does not see that
    file -- only Compose's own subprocess reads it (Codex review
    MEDIUM-002). Never logs the value itself."""
    dotenv_path = REPO_ROOT / ".env"
    if not dotenv_path.is_file():
        return None
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        return value or None
    return None


def _openai_key_available() -> bool:
    """True if OPENAI_API_KEY will actually reach the `api` container --
    either already in this process's own environment, or resolvable from
    the repo-root `.env` file the documented `cp .env.example .env` quick
    start populates and that Compose itself reads for `${VAR}`
    interpolation. Checking `os.environ` alone (the previous behavior)
    could report "no key" for a stack that actually received one through
    `.env`, silently skipping the generator/`mrag ask` assertions on a
    fully-configured stack (Codex review MEDIUM-002)."""
    return bool(os.environ.get("OPENAI_API_KEY") or _dotenv_value("OPENAI_API_KEY"))


class SmokeTestError(Exception):
    """An assertion failed (exit code 1) -- distinct from a precondition
    failure (exit code 2, e.g. no docker binary on PATH at all)."""


def _run_streaming(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def _run_captured(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    return result


def _require_docker_compose() -> list[str]:
    if shutil.which("docker") is None:
        print("ERROR: 'docker' not found on PATH.", file=sys.stderr)
        raise SystemExit(2)
    probe = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if probe.returncode != 0:
        print("ERROR: 'docker compose' (the v2 plugin) is not available.", file=sys.stderr)
        raise SystemExit(2)
    return ["docker", "compose"]


def _dump_logs(compose: list[str]) -> None:
    print("\n--- docker compose logs (for diagnosis) ---", file=sys.stderr)
    subprocess.run([*compose, "logs", "--no-color"], cwd=REPO_ROOT)


def _wait_for_health(url: str) -> None:
    deadline = time.monotonic() + HEALTH_POLL_DEADLINE
    last_error = ""
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=5.0)
        except httpx.HTTPError as exc:
            last_error = str(exc)
            time.sleep(HEALTH_POLL_INTERVAL)
            continue
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") != "ok" or not body.get("pipeline"):
                raise SmokeTestError(f"/health returned 200 but an unexpected body: {body}")
            print(f"/health OK: {body}")
            return
        if 400 <= resp.status_code < 500:
            # A 4xx from /health is a real misconfiguration (it takes no
            # input and never requires auth) -- not something more time
            # will fix, so fail fast instead of exhausting the deadline.
            raise SmokeTestError(f"/health returned {resp.status_code}: {resp.text}")
        last_error = f"HTTP {resp.status_code}: {resp.text}"
        time.sleep(HEALTH_POLL_INTERVAL)
    raise SmokeTestError(
        f"/health never returned 200 within {HEALTH_POLL_DEADLINE:.0f}s. Last error: {last_error}"
    )


def _fetch_ready(url: str) -> dict:
    resp = httpx.get(f"{url}/ready", timeout=10.0)
    if resp.status_code not in (200, 503):
        raise SmokeTestError(f"/ready returned an unexpected HTTP status {resp.status_code}")
    body = resp.json()
    if body.get("status") not in ("healthy", "degraded", "unready"):
        raise SmokeTestError(f"/ready 'status' is not a real ReadinessState value: {body}")
    if not isinstance(body.get("dependencies"), list):
        raise SmokeTestError(f"/ready is missing a 'dependencies' list: {body}")
    return body


def _dependency(report: dict, role: str) -> dict | None:
    return next((d for d in report["dependencies"] if d.get("role") == role), None)


def _require_dependency_present(report: dict, role: str) -> dict:
    """Confirms /ready has an entry for `role`, without requiring it
    healthy yet. Used for the `indexer` role before ingestion has run
    (Codex review HIGH-001) -- a fresh Qdrant volume has no `documents`
    collection until ingestion creates it, so an unhealthy indexer at this
    point is expected, honest behavior, not a defect."""
    dep = _dependency(report, role)
    if dep is None:
        raise SmokeTestError(f"/ready has no entry for role={role!r}: {report}")
    print(f"/ready role={role}: present (healthy={dep.get('healthy')}, pre-ingest)")
    return dep


def _assert_dependency_healthy(report: dict, role: str) -> None:
    """Checks `role`, and — only if it's unhealthy on the first probe —
    waits past the generator health-check cache window and re-probes
    exactly once before failing, in case the dependency was still warming
    up (Qdrant has no Compose-native healthcheck to gate startup ordering
    on — see compose.yaml's own comment on why)."""
    dep = _dependency(report, role)
    if dep is None:
        raise SmokeTestError(f"/ready has no entry for role={role!r}: {report}")
    if dep.get("healthy") is True:
        print(f"/ready role={role}: healthy")
        return
    print(
        f"/ready role={role} unhealthy on first probe ({dep.get('detail')}) -- "
        f"waiting {READY_RECHECK_DELAY:.0f}s and re-probing once before failing"
    )
    time.sleep(READY_RECHECK_DELAY)
    report2 = _fetch_ready(API_URL)
    dep2 = _dependency(report2, role)
    if dep2 is None or dep2.get("healthy") is not True:
        raise SmokeTestError(f"/ready role={role} still unhealthy after retry: {dep2}")
    print(f"/ready role={role}: healthy (after retry)")


def _check_migrate_succeeded(compose: list[str]) -> None:
    result = _run_captured([*compose, "ps", "migrate", "--format", "json", "--all"])
    if result.returncode != 0 or not result.stdout.strip():
        raise SmokeTestError(
            "Could not read the 'migrate' service's status via 'docker compose ps'."
        )
    # `docker compose ps --format json` has emitted either one JSON object
    # per line (NDJSON) or a single JSON array across different Compose v2
    # releases -- handle both rather than assume one, since this can't be
    # verified against a real `docker compose` binary in this environment.
    raw = result.stdout.strip()
    try:
        parsed = json.loads(raw)
        entries = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not entries:
        raise SmokeTestError("'migrate' service not found in 'docker compose ps' output.")
    exit_code = entries[0].get("ExitCode")
    if exit_code != 0:
        raise SmokeTestError(
            f"'migrate' service exited with code {exit_code} (expected 0) -- schema "
            "migration failed; see the logs dumped above/`docker compose logs migrate`."
        )
    print("migrate service: exited 0 (schema migration succeeded)")


def _mrag_exec(compose: list[str], *args: str) -> None:
    result = _run_captured([*compose, "exec", "-T", "api", "mrag", *args])
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SmokeTestError(f"'mrag {' '.join(args)}' failed (exit {result.returncode}).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test compose.yaml's full local stack.")
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail (instead of skipping) the generator-role/mrag-ask assertions when "
        "OPENAI_API_KEY is not set -- for a CI job with a real key configured.",
    )
    parser.add_argument(
        "--keep-up",
        action="store_true",
        help="On success, do not run 'docker compose down' afterward. On failure, the "
        "stack is always left running regardless of this flag, for live diagnosis.",
    )
    parser.add_argument(
        "--manifest",
        default="docker/local-hybrid-rag.yaml",
        help="In-container manifest passed to 'mrag ingest'/'mrag ask' (default: the same "
        "one compose.yaml's api service itself uses).",
    )
    args = parser.parse_args()

    have_llm_key = _openai_key_available()
    if args.require_llm and not have_llm_key:
        print("ERROR: --require-llm was passed but OPENAI_API_KEY is not set.", file=sys.stderr)
        return 2

    compose = _require_docker_compose()
    run_llm_checks = have_llm_key or args.require_llm

    up_rc = _run_streaming([*compose, "up", "-d", "--build"])
    if up_rc != 0:
        print(f"\nSMOKE TEST: FAIL -- 'docker compose up' exited {up_rc}", file=sys.stderr)
        _dump_logs(compose)
        return 1

    try:
        _wait_for_health(API_URL)
        _check_migrate_succeeded(compose)

        pre_ingest_report = _fetch_ready(API_URL)
        _assert_dependency_healthy(pre_ingest_report, "audit_sink")
        # Not asserted healthy yet -- see _require_dependency_present's own
        # docstring and HIGH-001 in the module docstring above.
        _require_dependency_present(pre_ingest_report, "indexer")

        if run_llm_checks:
            _assert_dependency_healthy(pre_ingest_report, "generator")

        _mrag_exec(compose, "ingest", "examples/simple_qa/docs", "--manifest", args.manifest)

        # The `documents` collection now exists -- this is the real proof
        # ingestion worked, not merely that the command exited 0.
        post_ingest_report = _fetch_ready(API_URL)
        _assert_dependency_healthy(post_ingest_report, "indexer")

        if run_llm_checks:
            _assert_dependency_healthy(post_ingest_report, "generator")
            if post_ingest_report.get("status") != "healthy":
                raise SmokeTestError(
                    "An OpenAI API key is available but /ready's aggregate status "
                    f"is {post_ingest_report.get('status')!r}, not 'healthy': "
                    f"{post_ingest_report}"
                )
            _mrag_exec(compose, "ask", "What is RAG?", "--manifest", args.manifest)

    except SmokeTestError as exc:
        print(f"\nSMOKE TEST: FAIL -- {exc}", file=sys.stderr)
        _dump_logs(compose)
        print(
            "\nStack left running for diagnosis -- 'docker compose exec api ...' to "
            "investigate, 'docker compose down' when done.",
            file=sys.stderr,
        )
        return 1

    status_note = "(full, including llm)" if run_llm_checks else "(llm assertions skipped)"
    print(f"\nSMOKE TEST: PASS {status_note}")
    if args.keep_up:
        print("--keep-up: stack left running ('docker compose down' to stop it).")
    else:
        _run_streaming([*compose, "down"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
