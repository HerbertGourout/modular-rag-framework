"""Manifest-configured provider-egress enforcement (Lot 20,
docs/refactoring-plan.md — "Data Classification and LLM Egress Control").

Fail-closed by design, same discipline as `tenant_isolation.py` next to this
file: an unknown provider or an unclassified input with no explicit
permission denies, never allows. There is deliberately no `try`/`except`
here swallowing a lookup/construction error into "allow" — a malformed
`governance.egress_policy.config` fails at construction time
(`ConfigurationError`), not silently at the first real request.

Distinct from `PolicyEngine` (`security/policies/policy_engine.py`): that is
a broad, YAML-rule-driven layer evaluating arbitrary conditions against
query text. This is the narrower, classification-vs-provider-profile
boundary Lot 20 owns specifically — the two are independently optional and
may both be configured on the same manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modular_rag.contracts.egress import EgressDecision, EgressOperation
from modular_rag.core.enums import DataClassification, classification_rank
from modular_rag.core.errors import ConfigurationError


@dataclass(frozen=True)
class _ProviderProfile:
    local: bool
    max_classification: DataClassification | None


def _parse_classification(value: str, *, where: str) -> DataClassification:
    try:
        return DataClassification(value)
    except ValueError as exc:
        allowed = [level.value for level in DataClassification]
        raise ConfigurationError(
            f"{where}: {value!r} is not a valid DataClassification. Expected one of {allowed}."
        ) from exc


def _parse_provider_profile(provider: str, raw: dict[str, Any]) -> _ProviderProfile:
    local = bool(raw.get("local", False))
    if local:
        return _ProviderProfile(local=True, max_classification=None)
    max_classification_raw = raw.get("max_classification")
    if max_classification_raw is None:
        raise ConfigurationError(
            f"governance.egress_policy.config.providers.{provider!r} does not set 'local: "
            "true' and omits 'max_classification' — a non-local provider profile must state "
            "the highest classification it may receive. Fail-closed: this manifest cannot be "
            "wired until one is set."
        )
    max_classification = _parse_classification(
        max_classification_raw,
        where=f"governance.egress_policy.config.providers.{provider!r}.max_classification",
    )
    return _ProviderProfile(local=False, max_classification=max_classification)


class ManifestEgressPolicy:
    """Reference `EgressPolicy` implementation. Registered on
    `Container.egress_policy`.

    Optional for a manifest wiring only local or custom/unrecognized provider
    types — absent, `RAGEngine`/`LangGraphEngineAdapter` behave exactly as
    they did before this lot, same optionality as `TenantIsolationPolicy`.
    **Not optional** the moment a manifest wires one of this framework's own
    known built-in remote provider types (`openai`, `anthropic`,
    `openai-embeddings`, `orchestration.registry._KNOWN_REMOTE_PROVIDER_TYPES`)
    — `orchestration/registry.py::runtime_manifest_errors()` rejects such a
    manifest at `wire()` when this policy (with a covering `providers[...]`
    entry for that type) is absent, regardless of engine adapter (Lot 20
    corrective remediation, HIGH-001; see docs/adr/0016-provider-egress-control.md
    §2).

    Configuration (`governance.egress_policy.config`):

    ```yaml
    providers:
      sentence-transformers: {local: true}
      openai: {local: false, max_classification: confidential}
      anthropic: {local: false, max_classification: internal}
    default_classification: restricted  # optional; applied when a chunk/query
                                         # carries no explicit classification
    ```

    `providers` keys are the wired component's manifest `type:` string
    (`ComponentConfig.type` — e.g. "openai", not `Generator.name()`, which
    several adapters make dynamic/model-specific and therefore unstable as a
    policy-config key). A provider not listed here is denied, not silently
    allowed — see `check()`.
    """

    def __init__(
        self,
        providers: dict[str, dict[str, Any]] | None = None,
        default_classification: str = "restricted",
    ) -> None:
        raw_providers = providers or {}
        self._providers: dict[str, _ProviderProfile] = {
            provider: _parse_provider_profile(provider, profile)
            for provider, profile in raw_providers.items()
        }
        self._default_classification = _parse_classification(
            default_classification, where="governance.egress_policy.config.default_classification"
        )

    def name(self) -> str:
        return "manifest"

    @property
    def known_providers(self) -> frozenset[str]:
        """Public introspection: which provider type-strings this policy has
        a profile for. Used by `orchestration.registry.runtime_manifest_errors()`
        to reject an incompatible manifest before startup (a wired
        embedder/generator/reranker type with no matching profile) instead
        of deferring that failure to the first real request."""
        return frozenset(self._providers)

    def check(
        self,
        *,
        classification: DataClassification | None,
        provider: str,
        operation: EgressOperation,
    ) -> EgressDecision:
        profile = self._providers.get(provider)
        if profile is None:
            return EgressDecision(
                allowed=False,
                reason=f"no egress profile configured for provider {provider!r}",
                classification=classification,
                provider=provider,
                operation=operation,
            )
        if profile.local:
            return EgressDecision(
                allowed=True,
                reason="local provider — no network egress",
                classification=classification,
                provider=provider,
                operation=operation,
            )
        effective = classification if classification is not None else self._default_classification
        assert profile.max_classification is not None  # non-local profiles always set one
        if classification_rank(effective) > classification_rank(profile.max_classification):
            return EgressDecision(
                allowed=False,
                reason=(
                    f"classification {effective.value!r} exceeds provider {provider!r}'s "
                    f"max_classification {profile.max_classification.value!r}"
                ),
                classification=classification,
                provider=provider,
                operation=operation,
            )
        return EgressDecision(
            allowed=True,
            reason=f"classification {effective.value!r} within provider's declared ceiling",
            classification=classification,
            provider=provider,
            operation=operation,
        )
