"""Manifest configuration resolution — Lot 9 (docs/refactoring-plan.md):
environment-variable interpolation, `secret://` references, configuration
precedence layering, capability (dry-run) validation, and v1<->v2 migration.

Deliberately separate from app/bootstrap.py: bootstrap.py stays a thin
"load and wire" facade; this module is where the new strictness lives, so
existing `load_manifest()`/`load_pipeline()` callers are unaffected unless
they opt into the new entry points here.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from modular_rag.contracts.manifests import (
    MANIFEST_SCHEMA_VERSIONS,
    ComponentConfig,
    PipelineManifest,
)
from modular_rag.contracts.secrets import SecretResolver
from modular_rag.core.errors import ConfigurationError, ManifestError
from modular_rag.orchestration.registry import ComponentRegistry, runtime_manifest_errors

_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SECRET_PREFIX = "secret://"

_V2_ONLY_SECTIONS = ("engine", "governance", "quality", "observability", "lifecycle")


class EnvSecretResolver:
    """Default `SecretResolver`: resolves `secret://NAME` against the `NAME`
    environment variable. A stand-in until a real secret backend (OpenBao,
    per docs/refactoring/technology-candidates.md) is wired as a second
    implementation of the same Protocol."""

    def resolve(self, name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            raise ConfigurationError(
                f"Secret '{name}' is not set (checked environment variable '{name}')"
            )
        return value


def _interpolate_value(value: Any, resolver: SecretResolver) -> Any:
    if isinstance(value, str):
        if value.startswith(_SECRET_PREFIX):
            return resolver.resolve(value[len(_SECRET_PREFIX) :])

        def _sub(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise ConfigurationError(
                    f"Environment variable '{var_name}' referenced in manifest "
                    f"(as '${{{var_name}}}') is not set"
                )
            return env_value

        return _ENV_VAR_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _interpolate_value(v, resolver) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_value(v, resolver) for v in value]
    return value


def interpolate(raw: dict[str, Any], resolver: SecretResolver | None = None) -> dict[str, Any]:
    """Resolve `${VAR}` environment interpolation and `secret://NAME`
    references throughout a raw manifest dict, before pydantic validation.
    Closes the gap found in Lot 5: `secure-enterprise-rag.yaml`'s
    `${QDRANT_URL}` was never interpolated before this existed.
    """
    resolver = resolver or EnvSecretResolver()
    result = _interpolate_value(raw, resolver)
    assert isinstance(result, dict)  # raw is always a dict; narrows the type for callers
    return result


def _read_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ManifestError(f"Manifest not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"Invalid YAML in {p}: {exc}") from exc
    return raw or {}


def resolve_manifest(
    preset_path: str | Path,
    *,
    environment_path: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
    resolver: SecretResolver | None = None,
) -> PipelineManifest:
    """Layer manifest sources by precedence: preset YAML < environment-
    specific YAML < explicit CLI overrides < (pydantic field defaults fill
    in whatever none of the three layers set). Each layer is a shallow
    top-level dict merge — a later layer's key wholesale replaces an earlier
    layer's same key; component sections are not deep-merged field by field,
    to avoid ambiguous partial-override semantics (e.g. what does overriding
    only `retriever.config.k` while leaving `retriever.type` from the preset
    even mean, if the environment layer's `retriever.type` differs?).
    """
    merged: dict[str, Any] = dict(_read_yaml(preset_path))
    if environment_path is not None:
        merged.update(_read_yaml(environment_path))
    if cli_overrides:
        merged.update(cli_overrides)
    interpolated = interpolate(merged, resolver)
    try:
        return PipelineManifest.model_validate(interpolated)
    except Exception as exc:  # pydantic.ValidationError, re-raised as our own type
        raise ManifestError(f"Manifest validation failed: {exc}") from exc


def validate_capabilities(manifest: PipelineManifest, registry: ComponentRegistry) -> list[str]:
    """Dry-run validation: check every declared component `type:` exists in
    the registry WITHOUT instantiating anything. Returns a list of error
    strings (empty list = valid). Catches a typo'd or unregistered type
    before a full `wire()` attempt fails deep inside construction.
    """
    errors: list[str] = []

    def _check(role: str, cfg: ComponentConfig | None) -> None:
        if cfg is None:
            return
        available = registry.available_types(role)
        if cfg.type not in available:
            errors.append(
                f"No factory for role='{role}' type='{cfg.type}'. "
                f"Available: {sorted(available)}"
            )

    _check("chunker", manifest.chunker)
    _check("embedder", manifest.embedder)
    _check("indexer", manifest.indexer)
    _check("retriever", manifest.retriever)
    _check("reranker", manifest.reranker)
    _check("generator", manifest.generator)
    _check("guard", manifest.security)
    if manifest.governance:
        _check("tenant_policy", manifest.governance.tenant_policy)
        _check("policy_engine", manifest.governance.policy_engine)
        _check("redactor", manifest.governance.redactor)
        _check("review_queue", manifest.governance.review_queue)
        _check("audit_sink", manifest.governance.audit_sink)
        # The tenant_enforcement/tenant_policy consistency checks used to live
        # here, but this function is only reached through the bootstrap
        # loaders (load_pipeline/load_engine/load_application) — a direct
        # ComponentRegistry.wire() call (a public primitive) bypassed them
        # entirely (Codex review finding, Lot 1 second pass). Moved into
        # orchestration/registry.py::runtime_manifest_errors(), which both
        # this function (below) and wire() itself now share as one
        # enforcement point.
    if manifest.observability:
        _check("telemetry", manifest.observability.telemetry)
    if manifest.lifecycle:
        _check("lifecycle_ledger", manifest.lifecycle.ledger)
    errors.extend(runtime_manifest_errors(manifest))
    return errors


def migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """Purely additive migration: bump the version marker and add empty v2
    sections. Every v1 field is untouched — this is why the migration is
    safe to round-trip via `rollback_v2_to_v1`."""
    if raw.get("version") not in MANIFEST_SCHEMA_VERSIONS:
        raise ManifestError(
            f"Unknown manifest version {raw.get('version')!r}; expected one of "
            f"{MANIFEST_SCHEMA_VERSIONS}"
        )
    migrated = dict(raw)
    migrated["version"] = "2.0"
    migrated.setdefault("engine", {"adapter": "native", "config": {}})
    # tenant_enforcement is explicit, not omitted: a v1 manifest never enforced
    # tenant isolation, and migration must say so out loud (ADR-0007 §3) rather
    # than leave it as an implicit, easy-to-overlook absence.
    migrated.setdefault("governance", {"tenant_enforcement": False})
    migrated.setdefault("quality", {})
    migrated.setdefault("observability", {})
    migrated.setdefault("lifecycle", {})
    return migrated


def rollback_v2_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    """Strip v2-only sections and reset the version marker. Safe today
    because none of governance/quality/observability enforcement is
    implemented yet (Lots 11/13/10) — nothing load-bearing is lost. If any
    of those sections ever gain real enforcement behavior, this function
    must be revisited before it can still be called "safe."
    """
    rolled_back = {k: v for k, v in raw.items() if k not in _V2_ONLY_SECTIONS}
    rolled_back["version"] = "1.0"
    return rolled_back
