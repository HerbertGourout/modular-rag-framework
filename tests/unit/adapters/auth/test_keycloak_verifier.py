"""Unit tests for adapters/auth/keycloak_verifier.py — KeycloakTokenVerifier.

Real RS256 JWT signing/verification against a locally generated keypair — no
live Keycloak needed, `_get_jwks()` is monkeypatched to return the fixture's
own JWKS instead of making a network call. Skipped entirely if `pyjwt[crypto]`
is not installed (it is not declared in pyproject.toml — same "opt-in
infrastructure" precedent as adapters/audit/postgres_sink.py, Lot 10).
Install with `pip install pyjwt[crypto]>=2.8` to run these.
"""
from __future__ import annotations

import time

import pytest

jwt = pytest.importorskip("jwt")

from modular_rag.adapters.auth.keycloak_verifier import KeycloakTokenVerifier  # noqa: E402
from modular_rag.core.errors import AuthenticationError  # noqa: E402

ISSUER = "https://keycloak.example.com/realms/acme"
AUDIENCE = "modular-rag"
KID = "test-key-1"


@pytest.fixture()
def rsa_keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture()
def verifier(rsa_keypair, monkeypatch):
    private_key, public_key = rsa_keypair
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk["kid"] = KID
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    v = KeycloakTokenVerifier(issuer_url=ISSUER, audience=AUDIENCE)
    monkeypatch.setattr(v, "_get_jwks", lambda: {"keys": [jwk]})
    return v, private_key


def _sign(private_key, claims: dict, kid: str = KID) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _claims(**overrides):
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "tenant_id": "acme-corp",
        "realm_access": {"roles": ["analyst"]},
        "iat": now,
        "exp": now + 3600,
    }
    base.update(overrides)
    return base


def test_verify_accepts_a_validly_signed_token(verifier):
    v, private_key = verifier
    token = _sign(private_key, _claims())

    ctx = v.verify(token)

    assert ctx.tenant_id == "acme-corp"
    assert ctx.user_id == "user-123"
    assert ctx.roles == frozenset({"analyst"})


def test_verify_rejects_an_expired_token(verifier):
    v, private_key = verifier
    token = _sign(private_key, _claims(exp=int(time.time()) - 10))

    with pytest.raises(AuthenticationError):
        v.verify(token)


def test_verify_rejects_wrong_audience(verifier):
    v, private_key = verifier
    token = _sign(private_key, _claims(aud="someone-else"))

    with pytest.raises(AuthenticationError):
        v.verify(token)


def test_verify_rejects_wrong_issuer(verifier):
    v, private_key = verifier
    token = _sign(private_key, _claims(iss="https://not-our-keycloak.example.com/realms/acme"))

    with pytest.raises(AuthenticationError):
        v.verify(token)


def test_verify_rejects_a_token_signed_by_an_untrusted_key(verifier):
    """Same kid as the trusted key, but signed by a *different* private key —
    the exact forged-signature attack JWKS-based verification exists to
    catch."""
    v, _ = verifier
    from cryptography.hazmat.primitives.asymmetric import rsa

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign(other_key, _claims())

    with pytest.raises(AuthenticationError):
        v.verify(token)


def test_verify_rejects_an_unknown_kid(verifier):
    v, private_key = verifier
    token = _sign(private_key, _claims(), kid="some-other-kid")

    with pytest.raises(AuthenticationError, match="No matching JWKS key"):
        v.verify(token)


def test_verify_rejects_a_token_missing_the_tenant_claim(verifier):
    v, private_key = verifier
    claims = _claims()
    del claims["tenant_id"]
    token = _sign(private_key, claims)

    with pytest.raises(AuthenticationError, match="tenant_id"):
        v.verify(token)


def test_verify_rejects_a_token_missing_the_user_claim(verifier):
    v, private_key = verifier
    claims = _claims()
    del claims["sub"]
    token = _sign(private_key, claims)

    with pytest.raises(AuthenticationError, match="sub"):
        v.verify(token)


def test_verify_defaults_to_empty_roles_when_roles_claim_absent(verifier):
    v, private_key = verifier
    claims = _claims()
    del claims["realm_access"]
    token = _sign(private_key, claims)

    ctx = v.verify(token)

    assert ctx.roles == frozenset()


def test_name_reports_keycloak(verifier):
    v, _ = verifier
    assert v.name() == "keycloak"
