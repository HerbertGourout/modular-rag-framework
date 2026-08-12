"""Shared tenant fixture content and manifest-rendering helper for
tests/e2e/test_secure_preset_e2e.py and tests/e2e/_secure_preset_replay.py —
kept in one place so the two files can never silently drift apart (Codex
review: the manual reproduction path needs to ingest the exact same content
the pytest scenario asserts against, and both consumers need to resolve
`MRAG_TEST_QDRANT_URL`/`MRAG_TEST_POSTGRES_DSN` into the manifest the same
way — previously only the pytest fixture did this, so the standalone replay
script's `--manifest` pointed at the static, hardcoded-localhost template
regardless of those two environment variables).
"""
from __future__ import annotations

from pathlib import Path

import yaml

MANIFEST_TEMPLATE = Path(__file__).parent / "manifests" / "secure-deterministic-rag.yaml"


def render_manifest(
    dest_dir: Path, *, qdrant_url: str, postgres_dsn: str, template: Path = MANIFEST_TEMPLATE
) -> Path:
    """Render `template` (defaults to `MANIFEST_TEMPLATE`) with
    `qdrant_url`/`postgres_dsn` substituted into
    `indexer.config.url`/`governance.audit_sink.config.dsn`, write the result
    into `dest_dir`, and return its path. `dest_dir` must already exist and
    be writable — callers supply it (a pytest `tmp_path_factory` directory,
    or a `tempfile.mkdtemp()` result for the standalone script) so this
    function stays test-framework-agnostic. `template` is overridable so
    `_secure_preset_replay.py`'s `--manifest` argument can point at any
    compatibly-shaped manifest (one with both of those config keys) and
    still get the same env-var resolution applied.
    """
    raw = yaml.safe_load(template.read_text(encoding="utf-8"))
    raw["indexer"]["config"]["url"] = qdrant_url
    raw["governance"]["audit_sink"]["config"]["dsn"] = postgres_dsn
    rendered = Path(dest_dir) / template.name
    rendered.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return rendered


TENANT_A = "e2e-tenant-a"
TENANT_B = "e2e-tenant-b"

# Deliberately overlapping vocabulary ("quarterly revenue report ... sector
# ... Earth") — see test_secure_preset_e2e.py's module docstring for why:
# it's what makes that module's BM25 cross-tenant-match test meaningful
# instead of vacuous.
TENANT_A_CONTENT = (
    "The company's quarterly revenue report shows strong growth in the "
    "whale-watching tourism sector. Blue whales are the largest animals "
    "ever known to have lived on Earth, reaching lengths of up to 30 meters."
)
TENANT_B_CONTENT = (
    "The company's quarterly revenue report shows strong growth in the "
    "mountain climbing equipment sector. Mount Everest is the tallest "
    "mountain above sea level on Earth, standing at 8,849 meters."
)
