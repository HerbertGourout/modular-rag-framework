"""Unit-level (no live services) regression coverage for
`tests/e2e/_secure_preset_fixtures.render_manifest()` — the helper both
`tests/e2e/test_secure_preset_e2e.py`'s `manifest_path` fixture and the
standalone `tests/e2e/_secure_preset_replay.py` script use to resolve
`MRAG_TEST_QDRANT_URL`/`MRAG_TEST_POSTGRES_DSN` into the manifest actually
loaded (Codex review: a prior version of the replay script silently ignored
both variables, so this pins that non-default values genuinely reach the
rendered file both consumers load).

Lives under `tests/unit/e2e/` rather than mirroring
`tests/e2e/_secure_preset_fixtures.py`'s own location 1:1, following the
precedent of `tests/unit/scripts/test_check_layering.py` (testing
`scripts/check_layering.py`, also outside `src/modular_rag/`) — placed here
specifically so it runs as part of the fast, no-external-service
`tests/unit/` scope (`./scripts/check.sh full`), unlike anything under
`tests/e2e/` itself, which `check.sh`'s `e2e` gate only ever runs filtered
to `-m e2e` (see `scripts/check.sh::check_e2e()`) — an unmarked test placed
directly in `tests/e2e/` would never actually execute in this project's own
validation workflow.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tests.e2e._secure_preset_fixtures import MANIFEST_TEMPLATE, render_manifest


def test_render_manifest_substitutes_a_non_default_qdrant_url(tmp_path: Path) -> None:
    rendered = render_manifest(
        tmp_path,
        qdrant_url="http://custom-qdrant-host:9999",
        postgres_dsn="postgresql://postgres:postgres@localhost:5432/postgres",
    )

    parsed = yaml.safe_load(rendered.read_text(encoding="utf-8"))

    assert parsed["indexer"]["config"]["url"] == "http://custom-qdrant-host:9999"


def test_render_manifest_substitutes_a_non_default_postgres_dsn(tmp_path: Path) -> None:
    rendered = render_manifest(
        tmp_path,
        qdrant_url="http://localhost:6333",
        postgres_dsn="postgresql://custom-user:custom-pass@custom-pg-host:5433/customdb",
    )

    parsed = yaml.safe_load(rendered.read_text(encoding="utf-8"))

    assert (
        parsed["governance"]["audit_sink"]["config"]["dsn"]
        == "postgresql://custom-user:custom-pass@custom-pg-host:5433/customdb"
    )


def test_render_manifest_defaults_to_the_real_secure_deterministic_template(tmp_path: Path) -> None:
    """No `template=` override — proves the default really is the shipped
    e2e manifest both consumers rely on, not an arbitrary/stale copy."""
    rendered = render_manifest(
        tmp_path, qdrant_url="http://localhost:6333", postgres_dsn="postgresql://x/y"
    )

    parsed = yaml.safe_load(rendered.read_text(encoding="utf-8"))

    assert parsed["id"] == "secure-deterministic-e2e"
    assert rendered.name == MANIFEST_TEMPLATE.name


def test_render_manifest_result_still_validates_as_a_pipeline_manifest(tmp_path: Path) -> None:
    """The rendered file must stay schema-valid after substitution — a
    typo in render_manifest()'s key path would otherwise only surface much
    later, as a confusing KeyError deep inside registry.wire()."""
    from modular_rag.contracts.manifests import PipelineManifest

    rendered = render_manifest(
        tmp_path,
        qdrant_url="http://custom-host:6333",
        postgres_dsn="postgresql://u:p@custom-host:5432/db",
    )

    manifest = PipelineManifest.model_validate(yaml.safe_load(rendered.read_text(encoding="utf-8")))

    assert manifest.indexer.config["url"] == "http://custom-host:6333"
    assert manifest.governance is not None
    assert manifest.governance.audit_sink is not None
    assert manifest.governance.audit_sink.config["dsn"] == "postgresql://u:p@custom-host:5432/db"
