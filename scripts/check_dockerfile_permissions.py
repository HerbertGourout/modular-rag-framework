"""Non-root/permissions gate (Lot 9 -- an external plan; not this repo's own
docs/refactoring-plan.md Lot sequence).

Two static checks against the Dockerfile (and, for the second, compose.yaml),
no Docker daemon required:

  1. The FINAL build stage (never an earlier builder stage -- what that runs
     as never ships) ends up running as a non-root user: its last `USER`
     directive names a user created with a non-zero uid (via `useradd`/
     `adduser --uid N`), or is itself a non-zero numeric uid.
  2. Every directory a compose.yaml *named* volume mounts onto (bind mounts
     are skipped -- they inherit host filesystem ownership, not the image's)
     is pre-created with a `mkdir -p` in that final stage, with a `chown`
     between the mkdir and the `USER` switch if the mkdir itself ran while
     still root -- otherwise Docker seeds the volume's mount point as
     root:root the first time the container starts, and the non-root
     process can never write into it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"
COMPOSE_PATH = PROJECT_ROOT / "compose.yaml"

_FROM_RE = re.compile(r"^FROM\s+\S+", re.MULTILINE)
_USER_RE = re.compile(r"^USER\s+(\S+)", re.MULTILINE)


class PermissionsCheckError(Exception):
    """A structural problem was found in the Dockerfile itself (no FROM
    stage at all) -- distinct from an ownership/root finding, which is
    returned as a list of problem strings instead."""


def final_stage_text(dockerfile_text: str) -> str:
    """Text of the last `FROM ... AS <stage>` block only -- an earlier
    (builder) stage's USER/mkdir directives never ship in the final image
    and are irrelevant to what the container actually runs as."""
    starts = [m.start() for m in _FROM_RE.finditer(dockerfile_text)]
    if not starts:
        raise PermissionsCheckError("no 'FROM' stage found in the Dockerfile.")
    return dockerfile_text[starts[-1] :]


def _final_user(stage_text: str) -> str | None:
    users = _USER_RE.findall(stage_text)
    return users[-1] if users else None


def _useradd_uid(stage_text: str, username: str) -> int | None:
    """Looks for `--uid N ... username` or `... username ... --uid N` on the
    same (adduser/useradd) command, since either flag order is valid shell."""
    escaped = re.escape(username)
    for pattern in (
        rf"(?:useradd|adduser)[^\n]*--uid[= ](\d+)[^\n]*\b{escaped}\b",
        rf"(?:useradd|adduser)[^\n]*\b{escaped}\b[^\n]*--uid[= ](\d+)",
    ):
        m = re.search(pattern, stage_text)
        if m:
            return int(m.group(1))
    return None


def check_non_root_user(dockerfile_text: str) -> list[str]:
    stage_text = final_stage_text(dockerfile_text)
    user = _final_user(stage_text)
    if user is None:
        return ["the final build stage has no 'USER' directive (defaults to root)."]

    username = user.split(":", 1)[0]
    if username.isdigit():
        return [f"the final build stage's USER is numeric uid {username}."] if int(username) == 0 else []
    if username == "root":
        return ["the final build stage's USER is 'root'."]

    uid = _useradd_uid(stage_text, username)
    if uid is None:
        return [
            f"could not verify user {username!r}'s uid (no matching useradd/adduser "
            "--uid line found) -- add one, or an explicit numeric USER, so this can "
            "be checked."
        ]
    if uid == 0:
        return [f"user {username!r} was created with --uid 0 (root)."]
    return []


def named_volume_mount_targets(compose_text: str, service: str = "api") -> list[str]:
    """Mount-point paths the given service's *named* volumes (declared under
    the compose file's top-level `volumes:`) target -- bind mounts
    (`./host/path:...`) are skipped; they inherit host ownership, not the
    image's, so this check does not apply to them."""
    compose = yaml.safe_load(compose_text) or {}
    service_config = ((compose.get("services") or {}).get(service)) or {}
    named_volume_names = set((compose.get("volumes") or {}).keys())
    targets: list[str] = []
    for entry in service_config.get("volumes") or []:
        if not isinstance(entry, str) or ":" not in entry:
            continue
        source, _, rest = entry.partition(":")
        if source in named_volume_names:
            targets.append(rest.split(":", 1)[0])
    return targets


def check_cache_dirs_precreated(dockerfile_text: str, compose_text: str) -> list[str]:
    stage_text = final_stage_text(dockerfile_text)
    user_directives = list(_USER_RE.finditer(stage_text))
    user_start = user_directives[-1].start() if user_directives else None

    problems: list[str] = []
    for target in named_volume_mount_targets(compose_text):
        mkdir_matches = list(re.finditer(rf"mkdir\s+-p\s+{re.escape(target)}\b", stage_text))
        if not mkdir_matches:
            problems.append(
                f"named-volume mount target {target!r} is never 'mkdir -p'-created in "
                "the final build stage -- Docker will seed it root:root on first run."
            )
            continue
        if user_start is None:
            continue  # already reported as missing-USER by check_non_root_user
        created_before_user = all(m.start() < user_start for m in mkdir_matches)
        if created_before_user:
            between = stage_text[mkdir_matches[0].start() : user_start]
            if "chown" not in between:
                problems.append(
                    f"{target!r} is 'mkdir -p'-created before the final USER switch "
                    "with no matching 'chown' in between -- it will be root-owned."
                )
    return problems


def main() -> int:
    dockerfile_text = DOCKERFILE_PATH.read_text(encoding="utf-8")
    try:
        problems = check_non_root_user(dockerfile_text)
    except PermissionsCheckError as exc:
        print(f"check_dockerfile_permissions: FAIL\n  - {exc}")
        return 1

    if COMPOSE_PATH.exists():
        compose_text = COMPOSE_PATH.read_text(encoding="utf-8")
        problems += check_cache_dirs_precreated(dockerfile_text, compose_text)

    if problems:
        print("check_dockerfile_permissions: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("check_dockerfile_permissions: OK -- final stage is non-root, cache dirs pre-owned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
