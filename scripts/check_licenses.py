"""Dependency licence gate (Lot 16b, docs/refactoring-plan.md — "vulnerability
and licence gates").

Classifies every currently-installed dependency's declared licence against a
permissive allowlist. Anything not permissive must be named in
`.claude/license-baseline.txt` (mirrors `.claude/mypy-baseline.txt`'s and
`.claude/layering-baseline.txt`'s accepted-exception pattern) with a recorded
reason, or the gate fails — this is a ratchet against *new* non-permissive
dependencies, not a claim that every currently-baselined one is risk-free.

Reflects installed-environment state (what `pip-licenses` sees right now),
not source — run as part of CI's `supply-chain` job after `pip install
-e .[all]`, not part of `scripts/check.sh`'s local `quick`/`full` tiers.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / ".claude" / "license-baseline.txt"

# Deliberately conservative: only unambiguous, broadly permissive licence
# families. GPL/AGPL are excluded even when a marker below would otherwise
# match a dual-license string (see _is_permissive) — copyleft always needs a
# human decision, never an automatic pass.
_PERMISSIVE_MARKERS = (
    "mit",
    "bsd",
    "apache",
    "isc license",
    "isc",
    "python software foundation",
    "psf",
    "mozilla public license 2.0",
    "mpl-2.0",
    "unlicense",
    "cc0",
    "zlib",
    "historical permission notice",
    "0bsd",
    "boost software license",
)


def _is_permissive(license_text: str) -> bool:
    lowered = license_text.lower()
    if "gpl" in lowered:
        # Catches GPL, LGPL, AGPL alike -- copyleft in any strength always
        # needs a human decision (the baseline file), never an automatic
        # pass, even if the same string also contains a permissive marker
        # (dual-license strings mix freely, e.g. pymupdf's "GNU AFFERO GPL
        # 3.0 or Artifex Commercial License").
        return False
    return any(marker in lowered for marker in _PERMISSIVE_MARKERS)


def _load_baseline() -> dict[str, str]:
    if not BASELINE_PATH.exists():
        return {}
    baseline: dict[str, str] = {}
    for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, _, reason = stripped.partition("=")
        baseline[name.strip().lower()] = reason.strip()
    return baseline


def _installed_packages() -> list[dict[str, str]]:
    result = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dependency licence gate.")
    parser.parse_args()

    packages = _installed_packages()
    baseline = _load_baseline()

    violations: list[tuple[str, str, str]] = []
    accepted: list[tuple[str, str, str]] = []
    for pkg in packages:
        name, version, license_text = pkg["Name"], pkg["Version"], pkg["License"]
        if _is_permissive(license_text):
            continue
        if name.lower() in baseline:
            accepted.append((name, version, license_text))
            continue
        violations.append((name, version, license_text))

    if violations:
        print("Unapproved (non-permissive, non-baselined) licences found:")
        for name, version, license_text in violations:
            print(f"  {name}=={version}: {license_text}")
        rel = BASELINE_PATH.relative_to(PROJECT_ROOT).as_posix()
        print(
            f"\nAdd an entry to {rel} with a recorded reason to accept, "
            "or replace the dependency."
        )
        return 1

    if accepted:
        print(f"Accepted baseline exceptions: {len(accepted)}")
        for name, version, license_text in accepted:
            print(f"  {name}=={version}: {license_text} -- {baseline[name.lower()]}")

    print(f"Licence check passed ({len(packages)} packages checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
