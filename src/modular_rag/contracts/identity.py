"""Identity/tenant contract (Lot 11b, docs/refactoring-plan.md — "Propagate
authenticated identity and tenant through ExecutionContext").

`TenantContext` is the verified-identity output of a `TokenVerifier` — the
thing `contracts.engine.ExecutionContext.tenant_id` (Lot 7) and
`core.models.query.Query.tenant_id` get populated from once a caller
authenticates. Verification itself is delegated to an adapter
(`adapters.auth.keycloak_verifier.KeycloakTokenVerifier`, Lot 11b) that
implements this Protocol against a specific identity provider — this module
stays vendor-neutral, the same discipline `contracts/engine.py` follows for
the external-engine boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TenantContext:
    """A verified identity. Only ever constructed by a `TokenVerifier` that
    has successfully validated a token — never hand-constructed to represent
    an "anonymous" or "guest" caller; the fail-closed principle (Lot 11b)
    requires the absence of a `TenantContext` to mean "denied," not a
    special-cased empty one meaning "allowed."
    """

    tenant_id: str
    user_id: str
    roles: frozenset[str] = field(default_factory=frozenset)


@runtime_checkable
class TokenVerifier(Protocol):
    """Verify a bearer token and return the identity/tenant it authenticates.

    Implementations must raise (typically `core.errors.AuthenticationError`)
    on any invalid, expired, or unverifiable token — never return a
    placeholder `TenantContext` as a fallback. A caller that receives an
    exception here must treat the request as denied, not proceed with a
    default identity.
    """

    def verify(self, token: str) -> TenantContext: ...

    def name(self) -> str: ...
