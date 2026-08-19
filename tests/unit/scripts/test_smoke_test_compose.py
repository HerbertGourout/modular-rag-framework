"""Unit tests for the Compose smoke test's LLM-credential detection
(Codex review MEDIUM-002, Lot 8) -- the parts of scripts/smoke_test_compose.py
that don't require a running Docker Compose stack to exercise."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.smoke_test_compose import _dotenv_value, _openai_key_available


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture()
def _repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("scripts.smoke_test_compose.REPO_ROOT", tmp_path)
    return tmp_path


def test_process_environment_key_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-process-env")
    assert _openai_key_available() is True


def test_dotenv_only_key_is_detected(_repo_root: Path) -> None:
    (_repo_root / ".env").write_text("OPENAI_API_KEY=sk-from-dotenv\n", encoding="utf-8")
    assert _openai_key_available() is True


def test_dotenv_value_strips_quotes_and_whitespace(_repo_root: Path) -> None:
    (_repo_root / ".env").write_text(' OPENAI_API_KEY = "sk-quoted" \n', encoding="utf-8")
    assert _dotenv_value("OPENAI_API_KEY") == "sk-quoted"


def test_dotenv_ignores_comments_and_unrelated_keys(_repo_root: Path) -> None:
    (_repo_root / ".env").write_text(
        "# OPENAI_API_KEY=sk-commented-out\nPOSTGRES_USER=postgres\n",
        encoding="utf-8",
    )
    assert _dotenv_value("OPENAI_API_KEY") is None


def test_missing_key_in_both_sources_is_not_available(_repo_root: Path) -> None:
    (_repo_root / ".env").write_text("POSTGRES_USER=postgres\n", encoding="utf-8")
    assert _openai_key_available() is False


def test_missing_dotenv_file_is_not_available(_repo_root: Path) -> None:
    assert _openai_key_available() is False
