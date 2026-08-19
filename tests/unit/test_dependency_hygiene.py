"""Regression test for the four dependencies removed in Lot 9 (external plan;
not this repo's own docs/refactoring-plan.md Lot sequence) as verified-dead:
zero imports anywhere in src/, tests/, or manifests/ (including
manifests/blueprints/) before removal. Guards against silent re-addition --
if one of these is ever genuinely needed again, add it back deliberately
with a real usage, not as an accidental copy-paste of an old extras list."""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_REMOVED_FROM_BASE = {"pydantic-settings", "python-ulid"}
_REMOVED_FROM_V1 = {"cohere", "langchain-text-splitters"}


def _load_pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _names(requirement_strings: list[str]) -> set[str]:
    return {req.split(">=")[0].split("[")[0].split("==")[0].strip().lower() for req in requirement_strings}


def test_dead_dependencies_are_absent_from_base_dependencies() -> None:
    pyproject = _load_pyproject()
    base_names = _names(pyproject["project"]["dependencies"])
    assert base_names.isdisjoint(_REMOVED_FROM_BASE)


def test_dead_dependencies_are_absent_from_v1_extra() -> None:
    pyproject = _load_pyproject()
    v1_names = _names(pyproject["project"]["optional-dependencies"]["v1"])
    assert v1_names.isdisjoint(_REMOVED_FROM_V1)
