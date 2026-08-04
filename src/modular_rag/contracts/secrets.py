"""Secret resolution for manifest configuration (Lot 9, docs/refactoring-plan.md)."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve a `secret://<name>` reference (found in a manifest's raw YAML)
    to its actual value. `app.config_resolution.EnvSecretResolver` is the
    default, environment-variable-backed implementation; a real secret
    backend (OpenBao, per docs/refactoring/technology-candidates.md) is a
    later, separate adapter implementing this same Protocol.
    """

    def resolve(self, name: str) -> str: ...
