"""Unit tests for the non-root/cache-permissions gate (Lot 9,
scripts/check_dockerfile_permissions.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_dockerfile_permissions import (
    PermissionsCheckError,
    check_cache_dirs_precreated,
    check_non_root_user,
    final_stage_text,
    named_volume_mount_targets,
)

DOCKERFILE_OK = """\
FROM python:3.12-slim AS builder
RUN echo builder-stage-user-is-irrelevant
USER root

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 mrag && \\
    mkdir -p /home/mrag/.cache/huggingface && \\
    chown -R mrag:mrag /home/mrag/.cache
USER mrag
"""

COMPOSE_OK = """\
services:
  api:
    volumes:
      - hf_cache:/home/mrag/.cache/huggingface
      - ./examples/simple_qa/docs:/app/examples/simple_qa/docs:ro
volumes:
  hf_cache:
"""


class TestFinalStageText:
    def test_returns_only_the_last_stage(self) -> None:
        text = final_stage_text(DOCKERFILE_OK)
        assert "runtime" in text
        assert "builder-stage-user-is-irrelevant" not in text

    def test_raises_when_no_from_present(self) -> None:
        with pytest.raises(PermissionsCheckError, match="no 'FROM'"):
            final_stage_text("RUN echo hi\n")


class TestCheckNonRootUser:
    def test_passes_a_correctly_created_non_root_user(self) -> None:
        assert check_non_root_user(DOCKERFILE_OK) == []

    def test_flags_missing_user_directive(self) -> None:
        text = "FROM python:3.12-slim AS runtime\nRUN echo hi\n"
        problems = check_non_root_user(text)
        assert any("no 'USER' directive" in p for p in problems)

    def test_flags_explicit_root(self) -> None:
        text = "FROM x AS runtime\nUSER root\n"
        assert any("is 'root'" in p for p in check_non_root_user(text))

    def test_flags_numeric_uid_zero(self) -> None:
        text = "FROM x AS runtime\nUSER 0\n"
        assert any("numeric uid 0" in p for p in check_non_root_user(text))

    def test_accepts_a_nonzero_numeric_uid(self) -> None:
        text = "FROM x AS runtime\nUSER 1000\n"
        assert check_non_root_user(text) == []

    def test_accepts_user_colon_group_form(self) -> None:
        text = "FROM x AS runtime\nRUN useradd --create-home --uid 1000 mrag\nUSER mrag:mrag\n"
        assert check_non_root_user(text) == []

    def test_flags_user_created_with_uid_zero(self) -> None:
        text = "FROM x AS runtime\nRUN useradd --uid 0 mrag\nUSER mrag\n"
        assert any("--uid 0" in p for p in check_non_root_user(text))

    def test_flags_unverifiable_user_with_no_useradd_line(self) -> None:
        text = "FROM x AS runtime\nUSER mrag\n"
        assert any("could not verify" in p for p in check_non_root_user(text))

    def test_only_the_final_stage_matters(self) -> None:
        """A root builder stage must never fail this check -- only what
        actually ships (the last FROM block) does."""
        text = (
            "FROM x AS builder\nUSER root\n\n"
            "FROM x AS runtime\nRUN useradd --create-home --uid 1000 mrag\nUSER mrag\n"
        )
        assert check_non_root_user(text) == []

    def test_useradd_flag_order_uid_after_name(self) -> None:
        text = "FROM x AS runtime\nRUN useradd mrag --uid 1000\nUSER mrag\n"
        assert check_non_root_user(text) == []


class TestNamedVolumeMountTargets:
    def test_returns_only_named_volume_targets(self) -> None:
        targets = named_volume_mount_targets(COMPOSE_OK)
        assert targets == ["/home/mrag/.cache/huggingface"]

    def test_bind_mounts_are_skipped(self) -> None:
        targets = named_volume_mount_targets(COMPOSE_OK)
        assert "/app/examples/simple_qa/docs" not in targets

    def test_no_volumes_section_returns_empty(self) -> None:
        assert named_volume_mount_targets("services:\n  api: {}\n") == []


class TestCheckCacheDirsPrecreated:
    def test_passes_when_mkdir_and_chown_precede_user(self) -> None:
        assert check_cache_dirs_precreated(DOCKERFILE_OK, COMPOSE_OK) == []

    def test_flags_a_named_volume_target_never_mkdird(self) -> None:
        dockerfile = "FROM x AS runtime\nRUN useradd --create-home --uid 1000 mrag\nUSER mrag\n"
        problems = check_cache_dirs_precreated(dockerfile, COMPOSE_OK)
        assert any("never 'mkdir -p'" in p for p in problems)

    def test_flags_mkdir_before_user_switch_without_chown(self) -> None:
        dockerfile = (
            "FROM x AS runtime\n"
            "RUN useradd --create-home --uid 1000 mrag && mkdir -p /home/mrag/.cache/huggingface\n"
            "USER mrag\n"
        )
        problems = check_cache_dirs_precreated(dockerfile, COMPOSE_OK)
        assert any("no matching 'chown'" in p for p in problems)

    def test_mkdir_after_user_switch_is_fine_without_chown(self) -> None:
        """A non-root user creating its own directory after the USER switch
        naturally owns it -- no chown needed in that ordering."""
        dockerfile = (
            "FROM x AS runtime\n"
            "RUN useradd --create-home --uid 1000 mrag\n"
            "USER mrag\n"
            "RUN mkdir -p /home/mrag/.cache/huggingface\n"
        )
        assert check_cache_dirs_precreated(dockerfile, COMPOSE_OK) == []


class TestRealRepoFiles:
    def test_the_actual_dockerfile_and_compose_pass(self) -> None:
        root = Path(__file__).resolve().parents[3]
        dockerfile_text = (root / "Dockerfile").read_text(encoding="utf-8")
        compose_text = (root / "compose.yaml").read_text(encoding="utf-8")

        assert check_non_root_user(dockerfile_text) == []
        assert check_cache_dirs_precreated(dockerfile_text, compose_text) == []
