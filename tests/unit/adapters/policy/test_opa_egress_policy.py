"""Unit tests for adapters/policy/opa_egress_policy.py — OpaEgressPolicy.

No OPA server is involved: every HTTP exchange goes through
`httpx.MockTransport`. The real dialogue with OPA (Rego evaluation, `/health`)
is covered by tests/integration/test_opa_egress_policy.py.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from modular_rag.adapters.policy.opa_egress_policy import OpaEgressPolicy
from modular_rag.contracts.egress import EgressOperation, EgressPolicy
from modular_rag.contracts.manifests import ComponentConfig, PipelineManifest
from modular_rag.core.enums import DataClassification, RetrievalMethod
from modular_rag.core.errors import ConfigurationError, EgressDeniedError
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.chunk import Chunk
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.resilience import CircuitBreaker
from modular_rag.orchestration.container import Container
from modular_rag.orchestration.engine import RAGEngine

_URL = "http://opa.test:8181"
_PROVIDERS = {"sentence-transformers": {"local": True}, "openai": {"local": False}}

Responder = Callable[[httpx.Request], httpx.Response]


class _FakeOpa:
    """An OPA stand-in that records every request. Responders are consumed in
    order; the last one repeats."""

    def __init__(self, *responders: Responder) -> None:
        self._responders = list(responders)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self._responders) > 1:
            return self._responders.pop(0)(request)
        return self._responders[0](request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def input_of(self, index: int) -> dict[str, Any]:
        return json.loads(self.requests[index].content)["input"]


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _answer(allowed: object, **extra: object) -> Responder:
    return lambda request: httpx.Response(
        200, json={"result": {"allowed": allowed, **extra}}
    )


def _status(code: int) -> Responder:
    return lambda request: httpx.Response(code)


def _raising(exc: Exception) -> Responder:
    def responder(request: httpx.Request) -> httpx.Response:
        raise exc

    return responder


def _policy(fake: _FakeOpa, **overrides: Any) -> OpaEgressPolicy:
    config: dict[str, Any] = {"url": _URL, "providers": _PROVIDERS}
    config.update(overrides)
    return OpaEgressPolicy(**config, transport=fake.transport())


def _check(
    policy: OpaEgressPolicy,
    classification: DataClassification | None = DataClassification.INTERNAL,
    provider: str = "openai",
    operation: EgressOperation = EgressOperation.GENERATE,
):
    return policy.check(classification=classification, provider=provider, operation=operation)


# --- decisions -----------------------------------------------------------------


def test_satisfies_the_egress_policy_protocol() -> None:
    assert isinstance(_policy(_FakeOpa(_answer(True))), EgressPolicy)


def test_a_local_provider_is_allowed_without_calling_opa() -> None:
    fake = _FakeOpa(_answer(False))

    decision = _check(
        _policy(fake),
        classification=DataClassification.RESTRICTED,
        provider="sentence-transformers",
    )

    assert decision.allowed is True
    assert fake.requests == []


def test_an_unknown_provider_is_denied_without_calling_opa() -> None:
    fake = _FakeOpa(_answer(True))

    decision = _check(_policy(fake), provider="an-unconfigured-provider")

    assert decision.allowed is False
    assert fake.requests == []


@pytest.mark.parametrize("allowed", [True, False])
def test_a_remote_provider_follows_the_opa_decision(allowed: bool) -> None:
    decision = _check(_policy(_FakeOpa(_answer(allowed))))

    assert decision.allowed is allowed


def test_opa_receives_only_content_free_fields() -> None:
    fake = _FakeOpa(_answer(True))

    _check(_policy(fake), classification=DataClassification.INTERNAL, provider="openai")

    request = fake.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/v1/data/modular_rag/egress/decision"
    assert json.loads(request.content) == {
        "input": {"classification": "internal", "provider": "openai", "operation": "generate"}
    }


def test_unclassified_content_is_sent_as_the_default_classification() -> None:
    fake = _FakeOpa(_answer(True))

    decision = _check(_policy(fake, default_classification="confidential"), classification=None)

    assert fake.input_of(0)["classification"] == "confidential"
    # Parity with ManifestEgressPolicy: the decision reports what the caller
    # supplied, not the default that was substituted for it.
    assert decision.classification is None


@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(lambda request: httpx.Response(200, json={}), id="undefined-result"),
        pytest.param(lambda request: httpx.Response(200, json={"result": True}), id="bare-bool"),
        pytest.param(_answer("true"), id="string-allowed"),
        pytest.param(lambda request: httpx.Response(200, json={"result": {}}), id="no-allowed"),
        pytest.param(lambda request: httpx.Response(200, content=b"not json"), id="not-json"),
        pytest.param(lambda request: httpx.Response(200, json=[1]), id="not-an-object"),
        pytest.param(_status(500), id="http-500"),
        pytest.param(_status(401), id="http-401"),
        pytest.param(_raising(httpx.ConnectError("connection refused")), id="connect-error"),
        pytest.param(_raising(httpx.ReadTimeout("read timed out")), id="timeout"),
    ],
)
def test_anything_but_a_well_formed_decision_denies(responder: Responder) -> None:
    decision = _check(_policy(_FakeOpa(responder)))

    assert decision.allowed is False
    assert "fail-closed" in decision.reason


def test_a_policy_authored_reason_is_never_surfaced() -> None:
    """ADR-0016 §4: `reason` is built from the decision's own fields only."""
    fake = _FakeOpa(_answer(False, reason="internal note about client ACME"))

    decision = _check(_policy(fake))

    assert decision.allowed is False
    assert "ACME" not in decision.reason
    assert "openai" in decision.reason


def test_a_bearer_token_is_sent_when_configured() -> None:
    fake = _FakeOpa(_answer(True))

    _check(_policy(fake, token="s3cret"))

    assert fake.requests[0].headers["Authorization"] == "Bearer s3cret"


# --- caching -------------------------------------------------------------------


def test_a_definitive_decision_is_cached_until_the_ttl_expires() -> None:
    fake = _FakeOpa(_answer(True))
    clock = _Clock()
    policy = _policy(fake, cache_ttl_seconds=30, clock=clock)

    _check(policy)
    _check(policy)
    assert len(fake.requests) == 1

    clock.now += 31
    _check(policy)
    assert len(fake.requests) == 2


def test_caching_can_be_disabled() -> None:
    fake = _FakeOpa(_answer(True))
    policy = _policy(fake, cache_ttl_seconds=0)

    _check(policy)
    _check(policy)

    assert len(fake.requests) == 2


def test_the_cache_is_keyed_by_classification_provider_and_operation() -> None:
    fake = _FakeOpa(_answer(True))
    policy = _policy(fake)

    _check(policy, classification=DataClassification.INTERNAL)
    _check(policy, classification=DataClassification.CONFIDENTIAL)
    _check(policy, operation=EgressOperation.EMBED)

    assert len(fake.requests) == 3


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(_status(500), id="http-500"),
        pytest.param(lambda request: httpx.Response(200, json={}), id="undefined"),
    ],
)
def test_a_failure_is_never_cached(failure: Responder) -> None:
    """A transient blip, or a policy not yet loaded, must not deny for a TTL."""
    policy = _policy(_FakeOpa(failure, _answer(True)))

    assert _check(policy).allowed is False
    assert _check(policy).allowed is True


# --- circuit breaker -----------------------------------------------------------


def test_an_open_circuit_denies_without_calling_opa() -> None:
    fake = _FakeOpa(_status(500))
    policy = _policy(fake, circuit_breaker=CircuitBreaker(failure_threshold=1, reset_timeout=60))

    _check(policy)
    decision = _check(policy)

    assert decision.allowed is False
    assert len(fake.requests) == 1


# --- configuration -------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"url": "opa.test:8181"}, "url"),
        ({"decision_path": "../etc/passwd"}, "decision_path"),
        ({"decision_path": "modular_rag/egress?pretty=true"}, "decision_path"),
        ({"decision_path": ""}, "decision_path"),
        (
            {"providers": {"openai": {"local": False, "max_classification": "internal"}}},
            "max_classification",
        ),
        ({"providers": {"openai": {"local": "yes"}}}, "local"),
        ({"providers": ["openai"]}, "providers"),
        ({"default_classification": "secret"}, "default_classification"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": 31}, "timeout_seconds"),
        ({"timeout_seconds": True}, "timeout_seconds"),
        ({"cache_ttl_seconds": -1}, "cache_ttl_seconds"),
        ({"cache_ttl_seconds": 301}, "cache_ttl_seconds"),
        ({"token": ""}, "token"),
    ],
)
def test_invalid_configuration_is_rejected_at_construction(
    overrides: dict[str, Any], fragment: str
) -> None:
    config: dict[str, Any] = {"url": _URL, "providers": _PROVIDERS, **overrides}

    with pytest.raises(ConfigurationError, match=fragment):
        OpaEgressPolicy(**config)


def test_a_rejected_url_is_never_echoed() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        OpaEgressPolicy(url="ftp://admin:hunter2@opa.test", providers=_PROVIDERS)

    assert "hunter2" not in str(excinfo.value)


# --- health --------------------------------------------------------------------


def _health_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={})


def test_health_reports_no_dependency_when_every_provider_is_local() -> None:
    fake = _FakeOpa(_health_ok)
    policy = _policy(fake, providers={"sentence-transformers": {"local": True}})

    assert policy.check_health() == []
    assert fake.requests == []


def test_health_is_healthy_when_opa_answers() -> None:
    fake = _FakeOpa(_health_ok)

    [health] = _policy(fake).check_health()

    assert health.healthy is True
    assert health.name == "opa"
    assert fake.requests[0].url.path == "/health"


def test_health_is_unhealthy_on_a_non_200() -> None:
    [health] = _policy(_FakeOpa(_status(503))).check_health()

    assert health.healthy is False
    assert health.detail == "http 503"


def test_health_never_leaks_exception_text() -> None:
    fake = _FakeOpa(_raising(httpx.ConnectError("opa.internal.corp:8181 refused")))

    [health] = _policy(fake).check_health()

    assert health.healthy is False
    assert "opa.internal.corp" not in (health.detail or "")


def test_health_reads_an_open_circuit_without_calling_opa() -> None:
    fake = _FakeOpa(_status(500))
    policy = _policy(fake, circuit_breaker=CircuitBreaker(failure_threshold=1, reset_timeout=60))
    _check(policy)

    [health] = policy.check_health()

    assert health.detail == "circuit open"
    assert len(fake.requests) == 1


def test_a_health_probe_never_resets_real_traffic_failure_accounting() -> None:
    """health-checks.md rule 8. Two failures open this circuit. A probe that
    went through the breaker would reset the count between them, and the
    fourth check below would reach OPA again."""
    fake = _FakeOpa(_status(500), _health_ok, _status(500))
    policy = _policy(fake, circuit_breaker=CircuitBreaker(failure_threshold=2, reset_timeout=60))

    _check(policy)
    [health] = policy.check_health()
    _check(policy)
    decision = _check(policy)

    assert health.healthy is True
    assert decision.allowed is False
    assert len(fake.requests) == 3


# --- behaviour through the native engine ---------------------------------------


class _OneHitRetriever:
    def retrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return [
            RetrievedChunk(
                chunk=Chunk(doc_id="d", content="context"),
                score=0.9,
                rank=1,
                retrieval_method=RetrievalMethod.HYBRID,
            )
        ]

    async def aretrieve(self, query, k=10):  # type: ignore[no-untyped-def]
        return self.retrieve(query, k)

    def name(self) -> str:
        return "one-hit-retriever"


class _CountingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, query, context, trace):  # type: ignore[no-untyped-def]
        self.calls += 1
        return Answer(query_id=query.id, text="must never be produced")

    async def agenerate(self, query, context, trace):  # type: ignore[no-untyped-def]
        return self.generate(query, context, trace)

    def name(self) -> str:
        return "counting-generator"


def test_the_native_engine_blocks_before_generation_when_opa_denies() -> None:
    """The EGRESS_DECISION=ENFORCED claim, end to end with this adapter: an OPA
    denial must stop the request before any content reaches the generator."""
    fake = _FakeOpa(_answer(False))
    manifest = PipelineManifest(
        id="opa-egress-unit",
        chunker=ComponentConfig(type="fake"),
        embedder=ComponentConfig(type="fake"),
        indexer=ComponentConfig(type="fake"),
        retriever=ComponentConfig(type="fake"),
        generator=ComponentConfig(type="fake"),
    )
    generator = _CountingGenerator()
    container = Container(manifest)
    container.register("chunker", object())
    container.register("embedder", object())
    container.register("indexer", object())
    container.register("retriever", _OneHitRetriever())
    container.register("generator", generator)
    container.register("egress_policy", _policy(fake, providers={"fake": {"local": False}}))

    with pytest.raises(EgressDeniedError):
        RAGEngine(container).answer("What is RAG?")

    assert generator.calls == 0
    assert fake.requests, "the decision must have come from OPA, not a local shortcut"
