"""Unit tests for app/container.py — Container.close() (Lot 14,
docs/refactoring-plan.md — "own and close clients/resources") and
Container.check_readiness() (Lot 6, "readiness and resilience").
"""
from __future__ import annotations

from modular_rag.app.container import Container
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.enums import ReadinessState
from modular_rag.core.models.health import DependencyHealth


class _ClosableComponent:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FailingCloseComponent:
    def close(self) -> None:
        raise RuntimeError("close failed")


class _NoCloseComponent:
    """No close() at all — most components (chunkers, evaluators) are like
    this; Container.close() must skip them without error."""


def _container() -> Container:
    manifest = PipelineManifest(
        id="test-pipeline",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    return Container(manifest)


def test_close_calls_close_on_every_closable_component():
    container = _container()
    indexer = _ClosableComponent()
    generator = _ClosableComponent()
    container.register("indexer", indexer)
    container.register("generator", generator)

    container.close()

    assert indexer.closed is True
    assert generator.closed is True


def test_close_skips_components_without_a_close_method():
    container = _container()
    container.register("chunker", _NoCloseComponent())

    container.close()  # must not raise


def test_close_continues_after_one_component_fails_to_close():
    container = _container()
    ok = _ClosableComponent()
    container.register("indexer", _FailingCloseComponent())
    container.register("generator", ok)

    container.close()  # must not raise

    assert ok.closed is True  # the failure didn't stop the rest from closing


# ---------------------------------------------------------------------------
# Lot 6 (readiness and resilience) — Container.check_readiness().
# ---------------------------------------------------------------------------


class _HealthCheckableComponent:
    def __init__(self, results: list[DependencyHealth]) -> None:
        self._results = results

    def check_health(self) -> list[DependencyHealth]:
        return self._results


def _healthy(name: str) -> _HealthCheckableComponent:
    return _HealthCheckableComponent([DependencyHealth(name=name, healthy=True)])


def _unhealthy(name: str) -> _HealthCheckableComponent:
    return _HealthCheckableComponent([DependencyHealth(name=name, healthy=False, detail="down")])


def test_check_readiness_is_healthy_when_every_checked_component_is_healthy():
    container = _container()
    container.register("indexer", _healthy("qdrant"))
    container.register("generator", _NoCloseComponent())  # no check_health(), skipped

    report = container.check_readiness()

    assert report.status == ReadinessState.HEALTHY
    assert len(report.dependencies) == 1


def test_check_readiness_is_healthy_when_nothing_registered_has_check_health():
    container = _container()
    container.register("chunker", _NoCloseComponent())

    report = container.check_readiness()

    assert report.status == ReadinessState.HEALTHY
    assert report.dependencies == []


def test_check_readiness_is_degraded_when_the_indexer_is_unhealthy():
    """"indexer" is *not* critical (orchestration-specialist review, Lot 6
    — revised from an earlier cut that made it critical): it's never read
    directly by answer()/retrieve(), only indirectly through whichever
    retriever is wired, and HybridRetriever (both shipped presets) already
    degrades gracefully around a down vector leg. Only ingest_chunks()
    calls it unconditionally — an ingest-path failure is out of /ready's
    scope by design (see _CRITICAL_ROLES's module-level comment)."""
    container = _container()
    container.register("indexer", _unhealthy("qdrant"))

    report = container.check_readiness()

    assert report.status == ReadinessState.DEGRADED


def test_check_readiness_is_unready_when_a_wired_audit_sink_is_unhealthy():
    """"audit_sink" is critical *when wired*: RAGEngine._audit() has no
    try/except around record(), so a down audit sink already fails every
    /answer call today — DEGRADED would misreport "still serving
    traffic"."""
    container = _container()
    container.register("indexer", _healthy("qdrant"))
    container.register("audit_sink", _unhealthy("postgres"))

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY


def test_check_readiness_is_unready_when_the_generator_is_unhealthy():
    """"generator" is critical (Codex review HIGH-001, second pass):
    `RAGEngine._run_steps()` calls `generator.generate()` with no
    try/except and no fallback anywhere in this codebase — a down
    generator already fails every `/answer` call today, exactly like a
    down audit sink."""
    container = _container()
    container.register("generator", _unhealthy("openai"))

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY


def test_check_readiness_is_unready_when_a_wired_egress_policy_is_unhealthy():
    """"egress_policy" is critical when it has something to probe: a policy
    that cannot reach its decision service (`OpaEgressPolicy` against a down
    OPA) denies every remote call fail-closed, so /answer already fails for a
    remote-provider pipeline. DEGRADED would misreport "still serving
    traffic"."""
    container = _container()
    container.register("egress_policy", _unhealthy("opa"))

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY


def test_check_readiness_is_degraded_when_a_non_critical_component_is_unhealthy():
    """"lifecycle_ledger" is never read on the query path
    (answer()/retrieve()) — its own failure degrades ingestion only."""
    container = _container()
    container.register("indexer", _healthy("qdrant"))
    container.register("lifecycle_ledger", _unhealthy("postgres"))

    report = container.check_readiness()

    assert report.status == ReadinessState.DEGRADED


def test_check_readiness_is_degraded_when_the_retriever_leg_is_unhealthy():
    """"retriever" is never critical here: HybridRetriever (both shipped
    presets) already falls back to whichever leg is still reachable."""
    container = _container()
    container.register("indexer", _healthy("qdrant"))
    container.register("retriever", _unhealthy("sparse-qdrant"))

    report = container.check_readiness()

    assert report.status == ReadinessState.DEGRADED


def test_check_readiness_is_unready_when_indexer_and_retriever_are_both_unhealthy():
    """Codex review HIGH-002 (Lot 6): neither role is individually critical,
    but if *both* the dense ("indexer") and lexical ("retriever") legs
    report every entry unhealthy, there is no confirmed usable retrieval
    capacity left at all — the exact topology `secure-enterprise-rag.yaml`
    creates when its single shared Qdrant server goes down (dense leg via
    `indexer`, sparse leg via `retriever`). "No unhandled exception" alone
    would leave this DEGRADED/200 even though the pipeline cannot serve a
    useful answer."""
    container = _container()
    container.register("indexer", _unhealthy("qdrant"))
    container.register("retriever", _unhealthy("sparse-qdrant"))

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY


def test_check_readiness_stays_degraded_when_only_indexer_is_unhealthy_and_retriever_is_silent():
    """The default `local-hybrid-rag` preset's lexical leg is in-memory
    BM25, which has no `check_health()` at all — "retriever" reports zero
    entries, not "unhealthy". A down Qdrant here must stay DEGRADED: BM25
    keeps serving lexical-only results on its own regardless of Qdrant's
    state, so real capacity remains (Codex review HIGH-002's escalation
    must not fire on an *absent* retriever report, only a genuinely
    unhealthy one)."""
    container = _container()
    container.register("indexer", _unhealthy("qdrant"))
    container.register("retriever", _NoCloseComponent())  # no check_health(), skipped entirely

    report = container.check_readiness()

    assert report.status == ReadinessState.DEGRADED


def test_check_readiness_prefers_unready_over_degraded_when_both_are_present():
    container = _container()
    container.register("indexer", _unhealthy("qdrant"))  # non-critical -> degraded on its own
    container.register("audit_sink", _unhealthy("postgres"))  # critical -> unready wins

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY


def test_check_readiness_collects_every_reported_dependency():
    container = _container()
    container.register("indexer", _healthy("qdrant"))
    container.register("audit_sink", _healthy("postgres"))

    report = container.check_readiness()

    names = {d.name for d in report.dependencies}
    assert names == {"qdrant", "postgres"}


def test_check_readiness_stamps_each_dependency_with_its_registered_role():
    """test-specialist/orchestration-specialist review, Lot 6: two
    components can share one `name()` — both Postgres adapters report
    "postgres" — so `role` (the registry key, not the adapter's own name)
    is what actually distinguishes a critical `audit_sink` from a
    non-critical `lifecycle_ledger` in the `/ready` payload."""
    container = _container()
    container.register("audit_sink", _healthy("postgres"))
    container.register("lifecycle_ledger", _healthy("postgres"))

    report = container.check_readiness()

    roles = {d.role for d in report.dependencies}
    assert roles == {"audit_sink", "lifecycle_ledger"}


def test_check_readiness_does_not_crash_when_a_component_check_health_raises():
    """test-specialist review, Lot 6: discovery is duck-typed (`hasattr`),
    so nothing stops a third-party or future component's `check_health()`
    from raising — mirrors `close()`'s own per-component `try/except`
    immediately above in this file, rather than letting `/ready` turn into
    an opaque 500."""

    class _RaisingComponent:
        def check_health(self) -> list[DependencyHealth]:
            raise RuntimeError("probe boom")

    container = _container()
    container.register("audit_sink", _RaisingComponent())

    report = container.check_readiness()

    assert report.status == ReadinessState.UNREADY
    assert report.dependencies[0].healthy is False
    assert report.dependencies[0].detail is not None
    assert report.dependencies[0].detail.startswith("unreachable (")


def test_check_readiness_never_leaks_a_raw_exception_message_onto_the_report():
    """Codex review MED-002 (Lot 6): `/ready` is unauthenticated — a fake
    secret embedded in a third-party component's exception message must
    never reach the public `ReadinessReport`, whether it comes from a
    normal `check_health()` return or (as here) from `check_health()`
    itself raising."""

    class _LeakyComponent:
        def check_health(self) -> list[DependencyHealth]:
            raise RuntimeError("connection to postgresql://admin:hunter2@10.0.0.5/audit failed")

    container = _container()
    container.register("audit_sink", _LeakyComponent())

    report = container.check_readiness()

    dumped = str([d.model_dump() for d in report.dependencies])
    assert "hunter2" not in dumped
    assert "10.0.0.5" not in dumped
