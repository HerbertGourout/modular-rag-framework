"""Modular RAG Framework — context OS for RAG and agentic systems."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Single authoritative version source (Lot 16b, docs/refactoring-plan.md —
# "one authoritative version source"). `pyproject.toml`'s `[project].version`
# is that source; this reads it back from installed package metadata instead
# of duplicating the literal, so the two can never drift. Falls back to
# "0.0.0+unknown" only for the unsupported case of importing this module
# from source without ever having run `pip install [-e] .` — no dist-info to
# read metadata from yet.
try:
    __version__ = _pkg_version("modular-rag")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
