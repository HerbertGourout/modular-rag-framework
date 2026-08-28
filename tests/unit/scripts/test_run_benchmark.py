"""Unit tests for the parts of scripts/run_benchmark.py that don't require a
running Qdrant to exercise (Batch 13, external plan — "Offline benchmark").
The full ingest-and-score flow is exercised by CI's `benchmark-gate` job
(.github/workflows/ci.yml), which does have a real Qdrant service container —
matching this repo's existing convention that Qdrant-dependent behavior is
proven in integration/e2e scope or a dedicated CI job, not mocked in
tests/unit/.
"""
from __future__ import annotations

import subprocess

import pytest
from scripts.run_benchmark import (
    DEFAULT_BASELINE,
    DEFAULT_DATASET,
    DEFAULT_MANIFEST,
    KNOWN_BENCHMARK_MANIFEST_ID,
    _git_commit_sha,
    _should_clear_collection,
)


def test_default_manifest_path_exists_on_disk() -> None:
    assert DEFAULT_MANIFEST.exists(), f"missing: {DEFAULT_MANIFEST}"


def test_default_dataset_path_exists_on_disk() -> None:
    assert DEFAULT_DATASET.exists(), f"missing: {DEFAULT_DATASET}"


def test_default_baseline_path_exists_on_disk() -> None:
    assert DEFAULT_BASELINE.exists(), f"missing: {DEFAULT_BASELINE}"


def test_git_commit_sha_returns_a_real_sha_in_this_checkout() -> None:
    """This test file itself only exists inside a real git checkout, so a
    real 40-character hex sha should always be resolvable here — a `None`
    result would mean `_git_commit_sha()`'s subprocess call regressed, not
    that this environment genuinely lacks git."""
    sha = _git_commit_sha()

    assert sha is not None
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_git_commit_sha_returns_none_when_git_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    assert _git_commit_sha() is None


# ---------------------------------------------------------------------------
# Codex review (pass 2, HIGH-004): the first corrective pass cleared
# whichever --manifest's collection was supplied, by default -- destructive
# against an arbitrary custom/shared/production collection. The decision is
# now: clear only the recognized benchmark manifest automatically, or any
# manifest the caller explicitly forces via --clear-collection.
# ---------------------------------------------------------------------------


def test_default_path_never_clears_an_unowned_custom_manifest() -> None:
    """The exact regression Codex reproduced: an ordinary custom-manifest
    invocation, with no flag, must not be destructive."""
    assert _should_clear_collection("my-production-pipeline", force_clear=False) is False


def test_known_benchmark_manifest_clears_automatically_without_a_flag() -> None:
    """The one case that should still auto-clear -- preserves MEDIUM-002's
    reproducibility fix for the documented default usage."""
    assert _should_clear_collection(KNOWN_BENCHMARK_MANIFEST_ID, force_clear=False) is True


def test_explicit_clear_collection_flag_forces_clearing_any_manifest() -> None:
    """A caller who has confirmed a custom collection is safe to wipe can
    still opt in explicitly."""
    assert _should_clear_collection("my-own-verified-safe-manifest", force_clear=True) is True


def test_clear_collection_flag_is_recognized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex review (pass 2, HIGH-004): --clear-collection (opt-IN, replacing
    the unsafe opt-out --no-clear-collection from the first corrective pass)
    must parse without an "unrecognized argument" error. Uses --help (exits
    before any modular_rag/Qdrant import happens) since this file's own
    convention is not to require a live Qdrant."""
    import sys

    from scripts.run_benchmark import main

    monkeypatch.setattr(sys, "argv", ["run_benchmark.py", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert "--clear-collection" in capsys.readouterr().out
