"""Subprocess helper for tests/e2e/test_secure_preset_e2e.py's restart
scenario — and a standalone manual-reproduction tool independent of pytest.

Loads the deterministic secure manifest and either ingests the two
deterministic tenant fixtures (`--ingest-fixtures`) or answers ONE question
for ONE tenant, printing a JSON result to stdout. Run as a genuinely
separate `python` process (via `subprocess.run`), not imported into the
test's own process — a same-process "build a second ApplicationService"
would not actually prove anything survives a restart, since it can't rule
out in-process module-level state quietly carrying over between the
"before" and "after" instances. This script has no such escape hatch: it is
a fresh interpreter with fresh module state every time it runs, exactly
like a real `mrag ask` invocation after a deployment restart.

Named with a leading underscore, and does not match pytest's `test_*.py`/
`*_test.py` collection pattern, so it is never collected as a test module
itself — `test_secure_preset_e2e.py` invokes it via
`subprocess.run([sys.executable, __file__, ...])`.

`MRAG_TEST_QDRANT_URL`/`MRAG_TEST_POSTGRES_DSN` (same convention as
`tests/integration/test_qdrant_store.py`/`test_postgres_audit_sink.py`, and
as `test_secure_preset_e2e.py` itself) are resolved here too — `--manifest`
is treated as a *template* to render those two values into (via the shared
`_secure_preset_fixtures.render_manifest()` helper), not loaded unchanged.
Codex review: an earlier version of this script loaded `--manifest` as-is,
so setting those two environment variables before running this script had
no effect — only the pytest fixture's own rendering step honored them,
leaving the standalone/manual path silently pointed at localhost
regardless of what was set.

Usage — manual reproduction (two steps; the module fixture's teardown drops
the Qdrant collection as soon as any pytest invocation targeting this
file's tests finishes, so "run one pytest test, then run this script"
never actually worked — ingest through this same standalone script,
independent of pytest's fixture lifecycle entirely):

    python tests/e2e/_secure_preset_replay.py \\
        --manifest tests/e2e/manifests/secure-deterministic-rag.yaml \\
        --ingest-fixtures

    python tests/e2e/_secure_preset_replay.py \\
        --manifest tests/e2e/manifests/secure-deterministic-rag.yaml \\
        --tenant-id e2e-tenant-a \\
        --question "What does the quarterly revenue report say about the whale-watching sector?"

To target non-default service locations, set the environment variables
before either command:

    MRAG_TEST_QDRANT_URL=http://myhost:6333 \\
    MRAG_TEST_POSTGRES_DSN=postgresql://user:pass@myhost:5432/mydb \\
    python tests/e2e/_secure_preset_replay.py --manifest ... --ingest-fixtures

`--ingest-fixtures` ingests `_secure_preset_fixtures.TENANT_A_CONTENT`/
`TENANT_B_CONTENT` for `TENANT_A`/`TENANT_B` — the exact content
`test_secure_preset_e2e.py` itself ingests and asserts against — and is
idempotent to *run once*, but re-running it re-ingests duplicate chunks (no
lifecycle ledger is configured on this manifest); drop the Qdrant collection
yourself between runs if you want a clean slate (see
`test_secure_preset_e2e.py::_drop_qdrant_collection_if_present` for the
exact mechanics, or just delete/recreate it via any Qdrant client).

`--tenant-id`/`--question` prints a JSON object
`{"text": ..., "citations": [{"chunk_id": ..., "source": ...}, ...]}` to
stdout on success. `--ingest-fixtures` prints `{"ingested": true}`. On a
denied/failed request, the underlying `ModularRAGError` propagates as a
non-zero exit with a traceback on stderr — `test_secure_preset_e2e.py`'s own
restart test invokes this with `subprocess.run(..., check=True)`, so a
denial there surfaces as a `CalledProcessError`, not a parsed result.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import structlog

# Script-relative import — this file's own directory is on sys.path[0] when
# run directly (`python tests/e2e/_secure_preset_replay.py`), which is the
# only supported way to run it (see this module's docstring).
from _secure_preset_fixtures import (
    TENANT_A,
    TENANT_A_CONTENT,
    TENANT_B,
    TENANT_B_CONTENT,
    render_manifest,
)

from modular_rag.app.public import load_application
from modular_rag.core.models.document import Document

# CI review finding: `structlog`'s default `logger_factory` is
# `PrintLoggerFactory`, which writes every `log.info()`/`log.warning()` call
# straight to stdout via `print()` unless configured otherwise. This
# script's entire contract is "prints exactly one JSON object to stdout"
# (see the module docstring) — any library log call reachable from
# `app.answer()`/`app.close()` (e.g. a Postgres/Qdrant adapter's own
# structured logging) would otherwise interleave with the `json.dump()`
# output below, and the parent test's `json.loads(result.stdout)` fails
# with "Extra data" as soon as anything logs. Redirect structlog's output
# to stderr here, before `main()` does any real work, so stdout stays
# reserved for the JSON payload alone.
structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

QDRANT_URL = os.environ.get("MRAG_TEST_QDRANT_URL", "http://localhost:6333")
POSTGRES_DSN = os.environ.get(
    "MRAG_TEST_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)


def _ingest_fixtures(app) -> None:  # type: ignore[no-untyped-def]
    doc_a = Document(
        source="tenant-a-quarterly-report.txt", content=TENANT_A_CONTENT, tenant_id=TENANT_A
    )
    doc_b = Document(
        source="tenant-b-quarterly-report.txt", content=TENANT_B_CONTENT, tenant_id=TENANT_B
    )
    for doc in (doc_a, doc_b):
        app.ingest_chunks(app.chunker.chunk(doc))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--tenant-id")
    parser.add_argument("--question")
    parser.add_argument(
        "--ingest-fixtures",
        action="store_true",
        help="Ingest the two deterministic tenant documents instead of answering a "
        "question — run this once before manual --tenant-id/--question reproduction.",
    )
    args = parser.parse_args()
    if not args.ingest_fixtures and (not args.tenant_id or not args.question):
        parser.error("--tenant-id and --question are required unless --ingest-fixtures is set")

    # TemporaryDirectory (not the bare mkdtemp() an earlier version used) so the rendered
    # manifest — which embeds the full POSTGRES_DSN, password included — is deleted on both
    # success and failure, not left on disk indefinitely across every invocation (Codex
    # review, MED-002).
    with tempfile.TemporaryDirectory(prefix="mrag-e2e-replay-") as tmp_dir:
        manifest_path = render_manifest(
            Path(tmp_dir),
            qdrant_url=QDRANT_URL,
            postgres_dsn=POSTGRES_DSN,
            template=Path(args.manifest),
        )

        app = load_application(str(manifest_path))
        try:
            if args.ingest_fixtures:
                _ingest_fixtures(app)
                result: dict[str, object] = {"ingested": True}
            else:
                answer = app.answer(args.question, tenant_id=args.tenant_id)
                result = {
                    "text": answer.text,
                    "citations": [
                        {"chunk_id": c.chunk_id, "source": c.source} for c in answer.citations
                    ],
                }
        finally:
            app.close()

    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
