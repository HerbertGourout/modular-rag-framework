"""Existing-graph adapter (Lot 22, ADR-0018): bootstrap gate, identity, isolation, fail-closed."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from modular_rag.app.bootstrap import load_engine
from modular_rag.contracts.assurance import EvidenceKind, EvidenceStatus
from modular_rag.contracts.engine import EngineRequest, ExecutionContext
from modular_rag.core.errors import (
    ConfigurationError,
    EngineCapabilityError,
    PolicyViolationError,
)
from modular_rag.core.models.query import Query

PRESET = "manifests/presets/existing-graph-app.yaml"


def _ctx(tenant: str | None = "tenant-a") -> ExecutionContext:
    return ExecutionContext(tenant_id=tenant, correlation_id="c1", request_id="r1")


def _request(text: str = "onboarding policy") -> EngineRequest:
    return EngineRequest(query=Query(text=text))


def _manifest(tmp_path: Path, old: str, new: str) -> Path:
    text = Path(PRESET).read_text(encoding="utf-8")
    assert old in text
    target = tmp_path / "m.yaml"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return target


def test_preset_loads_and_clears_the_profile_gate() -> None:
    assert load_engine(PRESET).name() == "existing-application:existing-graph-app"


def test_application_path_outside_the_allow_list_is_rejected(tmp_path: Path) -> None:
    path = _manifest(tmp_path, "examples.existing_graph_app.app", "os.path")

    with pytest.raises(ConfigurationError, match="allowed prefixes"):
        load_engine(path)


def test_unreachable_min_level_is_refused_at_startup(tmp_path: Path) -> None:
    path = _manifest(tmp_path, "min_level: l1", "min_level: l2")

    with pytest.raises(ConfigurationError):
        load_engine(path)


def test_run_scopes_results_to_the_context_tenant() -> None:
    result = load_engine(PRESET).run(_request(), _ctx("tenant-a"))

    assert "tenant-b" not in str(result)


def test_missing_tenant_fails_closed() -> None:
    with pytest.raises(PolicyViolationError):
        load_engine(PRESET).run(_request(), _ctx(None))


def test_streaming_is_not_offered() -> None:
    engine = load_engine(PRESET)

    async def consume() -> None:
        async for _ in engine.astream(_request(), _ctx()):
            pass

    with pytest.raises(EngineCapabilityError):
        asyncio.run(consume())


def test_conformance_report_never_claims_unsupported_evidence() -> None:
    report = load_engine(PRESET).conformance_report(_ctx())
    by_kind = {e.kind: e.status for e in report.evidence}

    assert by_kind[EvidenceKind.USAGE_COST] is EvidenceStatus.UNSUPPORTED
