"""OPA-backed provider-egress enforcement (ADR-0016 §4, "any future
`EgressPolicy` implementation"). Implements `contracts.egress.EgressPolicy` by
delegating the classification-vs-provider decision to an Open Policy Agent
server through its data API.

Why behind `EgressPolicy` and not `PolicyEngine`: `EgressPolicy` is an accepted
Protocol whose evidence (`EvidenceKind.EGRESS_DECISION`) the Lot 21 conformance
harness already probes, so this adapter changes no contract. `PolicyEngine` has
no Protocol at all; putting OPA behind it is ADR-0003's separate V4 item, a
contract decision deliberately not taken here.

Decided locally, by construction, whatever the Rego policy says:

- a provider absent from `providers` is denied without calling OPA;
- a provider declared `local: true` is allowed without calling OPA.

Both are cross-implementation invariants of the port
(`tests/contract/test_egress_conformance.py`), so neither may depend on an
operator's policy being correct. OPA decides only the genuinely
policy-dependent case: remote provider x effective classification x operation.
Providers must still be declared here because
`orchestration.registry.runtime_manifest_errors()` requires every wired
embedder/generator/reranker type to be covered by `providers` (ADR-0016 §2). A
provider declared here but missing from the Rego policy yields an undefined
decision, which denies.

What OPA receives is exactly `{"classification", "provider", "operation"}`: an
enum value, a manifest type string and an enum value. Never query text, chunk
content or any other caller content. The decision is content-free, which is
also what makes it safe to cache.

Fail-closed: an undefined result (no rule matched, OPA answers `{}`), a
malformed result, a non-200 status, a timeout, a transport error or an open
circuit all deny. `EgressDecision.reason` is always built here from the
decision's own fields and never copied from the policy's output (ADR-0016 §4:
content-free and bounded).

Caching: a definitive allow or deny is cached per (classification, provider,
operation) for `cache_ttl_seconds`. `RAGEngine.ingest_chunks()` checks every
chunk, so an uncached policy would make one HTTP call per embedded chunk.
Failures and undefined or malformed answers are never cached: a transient
network blip must not deny traffic for a whole TTL. The TTL is also the upper
bound on how long a tightened policy can take to apply, hence its ceiling.
"""
from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
import structlog

from modular_rag.contracts.egress import EgressDecision, EgressOperation
from modular_rag.core.enums import DataClassification
from modular_rag.core.errors import ConfigurationError
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    unhealthy_dependency,
)

log = structlog.get_logger(__name__)

_CONFIG = "governance.egress_policy.config"
# .claude/rules/health-checks.md rule 4: the probe's own bound, never the
# request-path timeout.
_HEALTH_CHECK_TIMEOUT = 2.0
_MAX_TIMEOUT_SECONDS = 30.0
# Ceiling on how stale a cached allow may be once a policy is tightened.
_MAX_CACHE_TTL_SECONDS = 300.0
# Slash-separated Rego package/rule segments only, appended to `/v1/data/`:
# no query string, no traversal, no scheme.
_DECISION_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*")
# A profile under `type: opa` carries only the local/remote flag. Anything else,
# notably `max_classification`, would be a ceiling that nothing enforces.
_PROFILE_KEYS = frozenset({"local"})


class _Outcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    UNDEFINED = "undefined"
    MALFORMED = "malformed"
    UNAVAILABLE = "unavailable"


class _OpaStatusError(Exception):
    """A non-200 answer from OPA. Raised inside the circuit breaker so that it
    counts as a dependency failure; never escapes this module."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"OPA answered HTTP {status_code}")
        self.status_code = status_code


@dataclass(frozen=True)
class _CacheEntry:
    allowed: bool
    expires_at: float


def _parse_classification(value: object) -> DataClassification:
    expected = [level.value for level in DataClassification]
    error = ConfigurationError(
        f"{_CONFIG}.default_classification: {value!r} is not a valid "
        f"DataClassification. Expected one of {expected}."
    )
    if not isinstance(value, str):
        raise error
    try:
        return DataClassification(value)
    except ValueError as exc:
        raise error from exc


def _parse_bounded(value: object, *, name: str, allow_zero: bool, maximum: float) -> float:
    where = f"{_CONFIG}.{name}"
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigurationError(f"{where} must be a number, got {value!r}.")
    number = float(value)
    if (number < 0 if allow_zero else number <= 0) or number > maximum:
        lower = ">= 0" if allow_zero else "> 0"
        raise ConfigurationError(f"{where} must be {lower} and <= {maximum:g}, got {number:g}.")
    return number


def _parse_local_flags(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise ConfigurationError(
            f"{_CONFIG}.providers must map each provider type to a profile, "
            "e.g. {openai: {local: false}}."
        )
    flags: dict[str, bool] = {}
    for provider, profile in raw.items():
        where = f"{_CONFIG}.providers.{provider!r}"
        settings = {} if profile is None else profile
        if not isinstance(settings, dict):
            raise ConfigurationError(f"{where} must be a mapping such as {{local: true}}.")
        unread = sorted(str(key) for key in set(settings) - _PROFILE_KEYS)
        if unread:
            raise ConfigurationError(
                f"{where} sets {unread}, which type 'opa' does not read: the OPA policy "
                "decides what a remote provider may receive. Remove them rather than keep a "
                "ceiling in the manifest that nothing enforces."
            )
        local = settings.get("local", False)
        if not isinstance(local, bool):
            raise ConfigurationError(f"{where}.local must be true or false, got {local!r}.")
        flags[str(provider)] = local
    return flags


def _parse_token(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"{_CONFIG}.token must be a non-empty string when set (its value is never echoed)."
        )
    return value


def _parse_decision(response: httpx.Response) -> _Outcome:
    """Only a JSON object whose `result` is an object with a boolean `allowed`
    is a decision. Anything else denies."""
    try:
        payload: object = response.json()
    except ValueError:
        return _Outcome.MALFORMED
    if not isinstance(payload, dict):
        return _Outcome.MALFORMED
    if "result" not in payload:
        # OPA's answer when nothing defines the document: no policy loaded, a
        # typo in `decision_path`, or a policy without a default.
        return _Outcome.UNDEFINED
    result = payload["result"]
    if not isinstance(result, dict) or not isinstance(result.get("allowed"), bool):
        return _Outcome.MALFORMED
    return _Outcome.ALLOW if result["allowed"] else _Outcome.DENY


def _reason(
    outcome: _Outcome, effective: DataClassification, provider: str, operation: EgressOperation
) -> str:
    subject = f"classification {effective.value!r} for provider {provider!r} ({operation.value})"
    reasons = {
        _Outcome.ALLOW: f"OPA policy allowed {subject}",
        _Outcome.DENY: f"OPA policy denied {subject}",
        _Outcome.UNDEFINED: f"OPA policy returned no decision for {subject}; denied (fail-closed)",
        _Outcome.MALFORMED: (
            f"OPA policy returned a malformed decision for {subject}; denied (fail-closed)"
        ),
        _Outcome.UNAVAILABLE: f"OPA decision unavailable for {subject}; denied (fail-closed)",
    }
    return reasons[outcome]


def _elapsed_ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


class OpaEgressPolicy:
    """`EgressPolicy` backed by an Open Policy Agent server. See this module's
    docstring for what is decided locally, what OPA decides, and why every
    failure denies.

    Configuration (`governance.egress_policy`, `type: opa`):

    ```yaml
    config:
      url: http://opa:8181
      decision_path: modular_rag/egress/decision   # POST /v1/data/<decision_path>
      providers:                                    # same coverage rule as type: manifest
        sentence-transformers: {local: true}
        openai: {local: false}
      default_classification: restricted            # applied to unclassified content
      timeout_seconds: 1.0
      cache_ttl_seconds: 30                         # 0 disables caching
      token: ${OPA_TOKEN}                           # optional bearer token
    ```

    The policy must define `{"allowed": true|false}` at `decision_path` for the
    input `{"classification": ..., "provider": ..., "operation": ...}`. Extra
    keys in the result are ignored; in particular a policy-authored `reason` is
    never surfaced (ADR-0016 §4).

    `circuit_breaker`, `transport` and `clock` are injection points for tests,
    not manifest settings.
    """

    def __init__(
        self,
        url: str,
        providers: dict[str, Any] | None = None,
        decision_path: str = "modular_rag/egress/decision",
        default_classification: str = "restricted",
        timeout_seconds: float = 1.0,
        cache_ttl_seconds: float = 30.0,
        token: str | None = None,
        *,
        circuit_breaker: CircuitBreaker | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        base_url = str(url)
        if not base_url.startswith(("http://", "https://")):
            raise ConfigurationError(
                f"{_CONFIG}.url must be an http:// or https:// URL (the value is not echoed, "
                "since a URL may embed credentials)."
            )
        path = str(decision_path).strip("/")
        if not _DECISION_PATH.fullmatch(path):
            raise ConfigurationError(
                f"{_CONFIG}.decision_path must be slash-separated Rego package and rule names "
                f"such as 'modular_rag/egress/decision', got {decision_path!r}."
            )
        self._url = base_url.rstrip("/")
        self._decision_url = f"/v1/data/{path}"
        self._local = _parse_local_flags({} if providers is None else providers)
        self._default_classification = _parse_classification(default_classification)
        self._timeout = _parse_bounded(
            timeout_seconds, name="timeout_seconds", allow_zero=False, maximum=_MAX_TIMEOUT_SECONDS
        )
        self._cache_ttl = _parse_bounded(
            cache_ttl_seconds,
            name="cache_ttl_seconds",
            allow_zero=True,
            maximum=_MAX_CACHE_TTL_SECONDS,
        )
        parsed_token = _parse_token(token)
        self._headers = {"Authorization": f"Bearer {parsed_token}"} if parsed_token else {}
        self._transport = transport
        # Constructing an httpx.Client opens no connection: nothing touches the
        # network until the first remote check.
        self._client = httpx.Client(
            base_url=self._url, timeout=self._timeout, headers=self._headers, transport=transport
        )
        self._circuit = circuit_breaker or CircuitBreaker()
        self._clock = clock
        self._cache: dict[tuple[DataClassification, str, EgressOperation], _CacheEntry] = {}
        self._cache_lock = threading.Lock()

    def name(self) -> str:
        return "opa"

    @property
    def known_providers(self) -> frozenset[str]:
        """Provider type strings this policy has a profile for, mirroring
        `ManifestEgressPolicy.known_providers`."""
        return frozenset(self._local)

    def close(self) -> None:
        self._client.close()

    def check(
        self,
        *,
        classification: DataClassification | None,
        provider: str,
        operation: EgressOperation,
    ) -> EgressDecision:
        local = self._local.get(provider)
        if local is None:
            return EgressDecision(
                allowed=False,
                reason=f"no egress profile configured for provider {provider!r}",
                classification=classification,
                provider=provider,
                operation=operation,
            )
        if local:
            return EgressDecision(
                allowed=True,
                reason="local provider — no network egress",
                classification=classification,
                provider=provider,
                operation=operation,
            )
        effective = (
            classification if classification is not None else self._default_classification
        )
        outcome = self._decide(effective, provider, operation)
        return EgressDecision(
            allowed=outcome is _Outcome.ALLOW,
            reason=_reason(outcome, effective, provider, operation),
            classification=classification,
            provider=provider,
            operation=operation,
        )

    def _decide(
        self, effective: DataClassification, provider: str, operation: EgressOperation
    ) -> _Outcome:
        key = (effective, provider, operation)
        with self._cache_lock:
            entry = self._cache.get(key)
        if entry is not None and entry.expires_at > self._clock():
            return _Outcome.ALLOW if entry.allowed else _Outcome.DENY
        outcome = self._query(effective, provider, operation)
        if self._cache_ttl > 0 and outcome in (_Outcome.ALLOW, _Outcome.DENY):
            fresh = _CacheEntry(
                allowed=outcome is _Outcome.ALLOW, expires_at=self._clock() + self._cache_ttl
            )
            with self._cache_lock:
                self._cache[key] = fresh
        return outcome

    def _query(
        self, effective: DataClassification, provider: str, operation: EgressOperation
    ) -> _Outcome:
        body = {
            "input": {
                "classification": effective.value,
                "provider": provider,
                "operation": operation.value,
            }
        }
        try:
            response = self._circuit.call(lambda: self._post(body))
        except CircuitBreakerOpenError:
            return _Outcome.UNAVAILABLE
        except Exception as exc:
            # Transport error, timeout or non-200, already counted by the
            # circuit breaker. Logged by type only, never with the request.
            log.warning(
                "opa_egress.decision_unavailable",
                provider=provider,
                operation=operation.value,
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            )
            return _Outcome.UNAVAILABLE
        outcome = _parse_decision(response)
        if outcome in (_Outcome.UNDEFINED, _Outcome.MALFORMED):
            log.warning(
                "opa_egress.no_usable_decision",
                provider=provider,
                operation=operation.value,
                outcome=outcome.value,
            )
        return outcome

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        response = self._client.post(self._decision_url, json=body)
        if response.status_code != 200:
            raise _OpaStatusError(response.status_code)
        return response

    def check_health(self) -> list[DependencyHealth]:
        """`contracts.health.HealthCheckable`, written against
        `.claude/rules/health-checks.md`:

        - reports nothing when every declared provider is local: no request path
          then depends on OPA, and `egress_policy` is a critical readiness role;
        - one attempt (rule 1) against OPA's read-only `GET /health` (rule 2), with
          the probe's own short timeout (rule 4);
        - a dedicated, throwaway client closed on every exit path, never the shared
          request-path client (rule 5);
        - reads the circuit breaker's state and never calls through it (rule 8), so
          a probe can neither reset real-traffic failure accounting nor take the
          half-open trial slot;
        - failures surface through `unhealthy_dependency()` or hand-written details,
          never raw exception text (rule 9).
        """
        if all(self._local.values()):
            return []
        t0 = time.perf_counter()
        if self._circuit.state == CircuitState.OPEN:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail="circuit open",
                    latency_ms=_elapsed_ms(t0),
                )
            ]
        try:
            with httpx.Client(
                base_url=self._url,
                timeout=min(self._timeout, _HEALTH_CHECK_TIMEOUT),
                headers=self._headers,
                transport=self._transport,
            ) as probe:
                response = probe.get("/health")
        except Exception as exc:
            return [unhealthy_dependency(self.name(), exc, _elapsed_ms(t0))]
        if response.status_code != 200:
            return [
                DependencyHealth(
                    name=self.name(),
                    healthy=False,
                    detail=f"http {response.status_code}",
                    latency_ms=_elapsed_ms(t0),
                )
            ]
        return [
            DependencyHealth(
                name=self.name(), healthy=True, detail="ok", latency_ms=_elapsed_ms(t0)
            )
        ]
