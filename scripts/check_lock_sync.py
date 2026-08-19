"""Reproducible-build gate (Lot 9 -- an external plan; not this repo's own
docs/refactoring-plan.md Lot sequence, unrelated and already used through
Lot 18 for different, completed work).

Verifies requirements-lock.txt actually, semantically covers what the
Docker image installs -- by resolved package names, not by trusting uv's
header-comment formatting (which varies across invocation styles: `--extra`
vs `--extra=`, `--all-extras`, absolute vs relative `-o` paths -- none of
that is a stable contract worth regexing).

Checks, in order:
  1. The Dockerfile's final-stage wheel-install line names a well-formed,
     non-empty set of extras, each of which actually exists in
     pyproject.toml's [project.optional-dependencies] (catches a typo pip
     itself would only warn about, never fail on).
  2. Every entry of requirements-lock.txt is a strict `name==version` pin
     (optionally hash-annotated across continuation lines) -- no `-e`, no
     bracketed extras, no unpinned specifier (catches a corrupted or
     hand-edited lock).
  3. Every direct dependency of pyproject.toml's base `dependencies` and of
     each extra the Dockerfile installs is present (name-normalized) in the
     lock. Deliberately a subset check, not set equality: the lock is
     allowed to cover more than the image installs (e.g. `dev`, kept for
     reproducible local/CI tooling installs) -- constraints only cap
     versions pip already decided to install, they never force an install.
  4. TRANSITIVE coverage (Codex review HIGH-003): direct-dependency coverage
     alone is not enough -- a lock missing an entire transitive branch
     (verified live: a lock naming only `pydantic`/`uvicorn` and omitting
     every `uvicorn[standard]` transitive -- click, h11, httptools, uvloop,
     watchfiles, websockets -- still passed check #3). This runs a real
     `pip install --dry-run --report` against the lock (hash-stripped --
     pip's hash-checking mode rejects a directly-specified local/editable
     target outright, verified directly) as a constraints file, for exactly
     the extras the Dockerfile installs, and asserts every package pip's
     resolver actually plans to install is present in the lock. Only
     authoritative when run on the same platform the image targets (Linux)
     -- pip's dependency-marker evaluation follows the *host* interpreter,
     not an overridable target the way `uv pip compile --python-platform`
     is; on a non-Linux host this sub-check is skipped with an explicit
     message rather than reporting Windows-only conditional packages
     (`pywin32`, `colorama`, ...) as false gaps, or silently claiming
     coverage it did not actually verify. On Linux, by contrast, this
     sub-check FAILS CLOSED (Codex review HIGH-003, round 2): any inability
     to complete the resolution there -- a timeout, a resolver conflict, a
     missing report -- is itself a hard failure, never a silent pass. The
     previous version treated every one of those cases the same as the
     legitimate non-Linux skip, so a CI run where pip could not even
     produce an answer still printed "OK" and exited 0 -- reproduced
     directly by forcing the Linux code path and a mocked resolver failure.
  5. Build backend coverage: pyproject.toml's `[build-system].requires`
     names a pinned Hatchling version (Codex review HIGH-002 -- a bare
     "hatchling" let `python -m build`'s isolated environment install
     whatever was newest at build time) and the Dockerfile's builder stage
     pins that same version explicitly for its `--no-isolation` build.
  6. `.dockerignore` does not exclude requirements-lock.txt from the build
     context, and the Dockerfile actually COPYs it into a build stage.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"
LOCK_PATH = PROJECT_ROOT / "requirements-lock.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
DOCKERIGNORE_PATH = PROJECT_ROOT / ".dockerignore"

_WHEEL_INSTALL_RE = re.compile(r'pip install[^\n]*"\$\{WHEEL_FILE\}\[([^\]]*)\]"')
_PKG_LINE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+?)(?:\s+\\)?$")
_HASH_CONTINUATION_RE = re.compile(r"^\s+--hash=sha256:[0-9a-f]{64}(?:\s+\\)?$")
_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_BUILD_SYSTEM_HATCHLING_RE = re.compile(r'requires\s*=\s*\[[^\]]*"hatchling==([^"]+)"')
_DOCKERFILE_HATCHLING_PIN_RE = re.compile(r"\bhatchling==(\S+)")
_DRY_RUN_TIMEOUT_SECONDS = 180


class LockSyncError(Exception):
    """A structural or coverage problem was found -- distinct from this
    script's own precondition failures (missing files), which raise
    FileNotFoundError instead."""


def _normalize(name: str) -> str:
    """PEP 503 normalization: case-insensitive; runs of -_. collapse to one -."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def extract_dockerfile_extras(dockerfile_text: str) -> list[str]:
    """The extras list from the final stage's `pip install "${WHEEL_FILE}[...]"`
    line. Raises if zero or more-than-one *distinct* such line is found --
    a silent pick-the-first-match would hide a Dockerfile that grew a second,
    divergent install line."""
    matches = []
    for line in dockerfile_text.splitlines():
        if line.strip().startswith("#"):
            continue
        m = _WHEEL_INSTALL_RE.search(line)
        if m:
            matches.append(m.group(1))
    if not matches:
        raise LockSyncError(
            "no 'pip install \"${WHEEL_FILE}[...]\"' line found in the Dockerfile."
        )
    if len(set(matches)) > 1:
        raise LockSyncError(
            f"multiple, differing wheel-install extras lines found in the Dockerfile: {matches}"
        )
    extras = [e.strip() for e in matches[0].split(",") if e.strip()]
    if not extras:
        raise LockSyncError("the Dockerfile's wheel-install extras list is empty.")
    return extras


def extract_lock_names(lock_text: str) -> set[str]:
    """Every pinned distribution name. Each entry is either a bare
    `name==version` line, or (when the lock was generated with
    `--generate-hashes`) a `name==version \\` line followed by one or more
    indented `--hash=sha256:...` continuation lines -- both are accepted;
    anything else on a non-comment, non-blank line is rejected."""
    names: set[str] = set()
    lines = lock_text.splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        m = _PKG_LINE_RE.match(stripped)
        if not m:
            raise LockSyncError(
                f"{LOCK_PATH.name}:{i + 1} is not a recognized lock entry "
                f"(strict 'name==version', no extras, no -e, no unpinned "
                f"specifier): {stripped!r}"
            )
        names.add(_normalize(m.group(1)))
        i += 1
        while i < len(lines) and (
            _HASH_CONTINUATION_RE.match(lines[i]) or lines[i].strip().startswith("#")
        ):
            i += 1
    return names


def _requirement_name(requirement_string: str) -> str:
    m = _REQ_NAME_RE.match(requirement_string.strip())
    if not m:
        raise LockSyncError(f"could not parse a distribution name from {requirement_string!r}")
    return _normalize(m.group(1))


def find_uncovered_dependencies(
    pyproject: dict, dockerfile_extras: list[str], lock_names: set[str]
) -> list[str]:
    """Every DIRECT dependency (base + each Dockerfile extra) not present in
    the lock. Necessary but not sufficient -- see
    find_uncovered_transitive_dependencies for the deeper check."""
    problems: list[str] = []
    optional = pyproject.get("project", {}).get("optional-dependencies", {})

    base_deps = pyproject.get("project", {}).get("dependencies", [])
    base_missing = [dep for dep in base_deps if _requirement_name(dep) not in lock_names]
    if base_missing:
        problems.append(f"base dependencies not pinned in {LOCK_PATH.name}: {base_missing}")

    for extra in dockerfile_extras:
        if extra not in optional:
            problems.append(
                f"Dockerfile extra {extra!r} does not exist in pyproject.toml's "
                "[project.optional-dependencies]."
            )
            continue
        missing = [dep for dep in optional[extra] if _requirement_name(dep) not in lock_names]
        if missing:
            problems.append(
                f"extra {extra!r} (installed by the Dockerfile) has direct dependencies "
                f"not pinned in {LOCK_PATH.name}: {missing}"
            )
    return problems


def _write_hashless_constraints(lock_text: str, destination: Path) -> None:
    """pip's hash-checking mode activates the instant ANY requirement in a
    constraints/requirements file carries a --hash, and then rejects a
    directly-specified local/editable install target outright ("cannot be
    installed when requiring hashes, because there is no single file to
    hash" -- reproduced directly). The dry-run below only needs *version*
    constraints, so hashes are stripped for this purpose only; the real
    Dockerfile install is a separate, unaffected code path."""
    lines = []
    for raw_line in lock_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or _HASH_CONTINUATION_RE.match(raw_line):
            continue
        m = _PKG_LINE_RE.match(stripped)
        if m:
            lines.append(f"{m.group(1)}=={m.group(2)}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_uncovered_transitive_dependencies(
    lock_text: str, dockerfile_extras: list[str], lock_names: set[str]
) -> tuple[list[str], str | None]:
    """Returns (problems, platform_skip_reason).

    platform_skip_reason is set (and problems is always []) ONLY for the one
    legitimate, non-authoritative case: not running on Linux (pip's marker
    evaluation follows the host interpreter, not an overridable target), so
    a Windows/macOS dev run cannot answer this question at all.

    On Linux -- the one platform this sub-check is authoritative on -- ANY
    inability to complete the resolution (pip missing, a timeout, a
    non-zero exit, a missing report) is now itself a `problems` entry, not
    a silent skip (Codex review HIGH-003, round 2: the previous version
    returned `([], skip_reason)` for every one of these cases too, so
    `main()` printed "OK" and exited 0 even when the check never actually
    ran on the platform where it is supposed to be the real answer --
    reproduced directly by forcing `platform.system()` to `"Linux"` and
    `subprocess.run` to raise `ResolutionImpossible`). A lock that is
    genuinely broken or incompatible with the target platform must fail
    the gate, not silently pass it."""
    if platform.system() != "Linux":
        return [], (
            f"skipped -- running on {platform.system()!r}, not Linux (the Docker image's "
            "real target platform). pip evaluates dependency markers against the host "
            "interpreter, not an overridable target, so this sub-check is only "
            "authoritative in CI (ubuntu-latest) or a Linux dev machine."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        constraints_path = Path(tmpdir) / "hashless-constraints.txt"
        report_path = Path(tmpdir) / "install-report.json"
        _write_hashless_constraints(lock_text, constraints_path)

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--quiet",
            "--no-cache-dir",
            "--ignore-installed",
            "-c",
            str(constraints_path),
            "--report",
            str(report_path),
            "-e",
            f"{PROJECT_ROOT}[{','.join(dockerfile_extras)}]",
        ]
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", NO_COLOR="1")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_DRY_RUN_TIMEOUT_SECONDS,
                cwd=PROJECT_ROOT,
                env=env,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [
                "could not run 'pip install --dry-run' to verify transitive coverage "
                f"({exc}) -- treated as a failure, not skipped, because this platform "
                "(Linux) is supposed to be authoritative for this check."
            ], None

        if result.returncode != 0 or not report_path.exists():
            return [
                "'pip install --dry-run --report' did not produce a report on Linux "
                f"(exit {result.returncode}) -- treated as a failure, not skipped, "
                f"because this platform is supposed to be authoritative for this check. "
                f"stderr:\n{result.stderr[-2000:]}"
            ], None

        report = json.loads(report_path.read_text(encoding="utf-8"))

    install_names = set()
    for item in report.get("install", []):
        name = item.get("metadata", {}).get("name")
        if name:
            install_names.add(_normalize(name))
    install_names.discard(_normalize("modular-rag"))  # the project installing itself

    missing = sorted(install_names - lock_names)
    if missing:
        return [
            f"pip's real dependency resolution for extras {dockerfile_extras} needs these "
            f"packages, but they are absent from {LOCK_PATH.name}: {missing}"
        ], None
    return [], None


def check_build_backend_pin(pyproject_text: str, dockerfile_text: str) -> list[str]:
    m = _BUILD_SYSTEM_HATCHLING_RE.search(pyproject_text)
    if not m:
        return [
            "pyproject.toml's [build-system].requires does not pin an exact "
            '"hatchling==VERSION" -- a bare/ranged requirement lets the isolated '
            "build environment install a different Hatchling each build."
        ]
    pinned_version = m.group(1)

    stage_texts = dockerfile_text.split("\nFROM ")
    builder_stage = next((s for s in stage_texts if "AS builder" in s.split("\n", 1)[0]), None)
    if builder_stage is None:
        return ["could not find a Dockerfile stage named 'builder' to check for a Hatchling pin."]

    dockerfile_pins = {
        _normalize("hatchling"): v
        for v in _DOCKERFILE_HATCHLING_PIN_RE.findall(builder_stage)
    }
    if not dockerfile_pins:
        return [
            f"pyproject.toml pins hatchling=={pinned_version}, but the Dockerfile's builder "
            "stage never installs a matching pinned 'hatchling==...' -- python -m build's "
            "isolated environment (or an un-pinned --no-isolation environment) would resolve "
            "its own, potentially different, version."
        ]
    dockerfile_version = next(iter(dockerfile_pins.values()))
    if dockerfile_version != pinned_version:
        return [
            f"pyproject.toml pins hatchling=={pinned_version} but the Dockerfile's builder "
            f"stage pins hatchling=={dockerfile_version} -- these must match."
        ]
    return []


def check_dockerignore_and_copy(dockerfile_text: str, dockerignore_text: str) -> list[str]:
    problems: list[str] = []
    for raw_line in dockerignore_text.splitlines():
        entry = raw_line.strip()
        if entry in (LOCK_PATH.name, f"/{LOCK_PATH.name}"):
            problems.append(f".dockerignore excludes {LOCK_PATH.name} from the build context.")
    if f"COPY {LOCK_PATH.name}" not in dockerfile_text and (
        f"COPY ./{LOCK_PATH.name}" not in dockerfile_text
    ):
        problems.append(f"the Dockerfile does not COPY {LOCK_PATH.name} into any build stage.")
    return problems


def run_static_checks(
    dockerfile_text: str, lock_text: str, pyproject: dict, pyproject_text: str, dockerignore_text: str
) -> tuple[list[str], list[str] | None]:
    """Returns (problems, extras). extras is None when extras extraction
    itself failed (already recorded in problems) -- callers must not
    attempt the transitive check in that case."""
    problems: list[str] = []
    try:
        extras = extract_dockerfile_extras(dockerfile_text)
    except LockSyncError as exc:
        return [str(exc)], None
    try:
        lock_names = extract_lock_names(lock_text)
    except LockSyncError as exc:
        return [str(exc)], None
    problems += find_uncovered_dependencies(pyproject, extras, lock_names)
    problems += check_build_backend_pin(pyproject_text, dockerfile_text)
    problems += check_dockerignore_and_copy(dockerfile_text, dockerignore_text)
    return problems, extras


def main() -> int:
    dockerfile_text = DOCKERFILE_PATH.read_text(encoding="utf-8")
    lock_text = LOCK_PATH.read_text(encoding="utf-8")
    pyproject_text = PYPROJECT_PATH.read_text(encoding="utf-8")
    pyproject = tomllib.loads(pyproject_text)
    dockerignore_text = (
        DOCKERIGNORE_PATH.read_text(encoding="utf-8") if DOCKERIGNORE_PATH.exists() else ""
    )

    problems, extras = run_static_checks(
        dockerfile_text, lock_text, pyproject, pyproject_text, dockerignore_text
    )

    skip_reason: str | None = None
    if extras is not None:
        lock_names = extract_lock_names(lock_text)
        transitive_problems, skip_reason = find_uncovered_transitive_dependencies(
            lock_text, extras, lock_names
        )
        problems += transitive_problems

    if problems:
        print("check_lock_sync: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nRegenerate the lock with the command in docs/guides/dependency-lock.md, "
            "or fix the Dockerfile/pyproject.toml drift directly."
        )
        return 1

    lock_names = extract_lock_names(lock_text)
    print(
        f"check_lock_sync: OK -- Dockerfile extras {extras} are fully covered by "
        f"{LOCK_PATH.name} ({len(lock_names)} pinned packages)."
    )
    if skip_reason:
        print(f"NOTE: transitive-resolution sub-check {skip_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
