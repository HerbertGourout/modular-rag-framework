"""Keycloak OIDC token verification (Lot 11b, docs/refactoring-plan.md — "Target
identity provider: Keycloak (OIDC)").

Lazy-imports PyJWT (with the `crypto` extra, for RS256 support) per
`.claude/.instructions.md` §4 — not declared in `pyproject.toml`, same
"opt-in infrastructure" precedent as `adapters/audit/postgres_sink.py`
(Lot 10). Install with: `pip install pyjwt[crypto]>=2.8`.

`httpx` (JWKS fetch) is a base project dependency already (`pyproject.toml`'s
core `dependencies`, not an optional extra) so it is imported at module
level, same as any other always-available library.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from modular_rag.contracts.identity import TenantContext
from modular_rag.core.errors import AuthenticationError


class KeycloakTokenVerifier:
    """Verifies RS256-signed JWTs against a Keycloak realm's JWKS endpoint.

    `tenant_claim`/`user_claim`/`roles_claim` are configurable (dotted-path
    for nested claims, e.g. Keycloak's default `realm_access.roles`) because
    claims mapping is realm/client-specific — this adapter does not assume a
    fixed schema, matching Lot 11a's data-classification-policy.md note that
    "claims mapping... is Lot 11b's design, not fixed" by any earlier lot.

    JWKS is fetched once and cached in-process; `jwks_ttl_seconds` controls
    when it's refetched (handles key rotation without a restart).
    """

    def __init__(
        self,
        issuer_url: str,
        audience: str,
        tenant_claim: str = "tenant_id",
        user_claim: str = "sub",
        roles_claim: str = "realm_access.roles",
        jwks_ttl_seconds: float = 3600.0,
    ) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        self._audience = audience
        self._tenant_claim = tenant_claim
        self._user_claim = user_claim
        self._roles_claim = roles_claim
        self._jwks_ttl_seconds = jwks_ttl_seconds
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0.0

    def _get_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks_cache is None or (now - self._jwks_fetched_at) > self._jwks_ttl_seconds:
            resp = httpx.get(f"{self._issuer_url}/protocol/openid-connect/certs", timeout=10.0)
            resp.raise_for_status()
            self._jwks_cache = resp.json()
            self._jwks_fetched_at = now
        return self._jwks_cache

    def verify(self, token: str) -> TenantContext:
        try:
            import jwt
        except ImportError as exc:
            raise ImportError(
                "pyjwt[crypto] is required for KeycloakTokenVerifier. "
                "Install it with: pip install pyjwt[crypto]>=2.8"
            ) from exc

        try:
            jwks = self._get_jwks()
            signing_key = self._signing_key_from_jwks(jwt, jwks, token)
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer_url,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            # Lot 11b: any verification failure — bad signature, expired, wrong
            # audience/issuer, malformed token, JWKS fetch failure — must deny,
            # never fall through to an "anonymous" identity.
            raise AuthenticationError(f"Token verification failed: {exc}") from exc

        tenant_id = self._get_claim(claims, self._tenant_claim)
        user_id = self._get_claim(claims, self._user_claim)
        if not tenant_id or not user_id:
            raise AuthenticationError(
                f"Token is missing required claim(s): "
                f"'{self._tenant_claim}' or '{self._user_claim}'."
            )
        roles = self._get_claim(claims, self._roles_claim) or []
        return TenantContext(
            tenant_id=str(tenant_id), user_id=str(user_id), roles=frozenset(roles)
        )

    @staticmethod
    def _signing_key_from_jwks(jwt_module: Any, jwks: dict[str, Any], token: str) -> Any:
        header = jwt_module.get_unverified_header(token)
        kid = header.get("kid")
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt_module.algorithms.RSAAlgorithm.from_jwk(key)
        raise AuthenticationError(f"No matching JWKS key for kid={kid!r}.")

    @staticmethod
    def _get_claim(claims: dict[str, Any], dotted_path: str) -> Any:
        value: Any = claims
        for part in dotted_path.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    def name(self) -> str:
        return "keycloak"
