"""Container entrypoint shim (Lot 16b, docs/refactoring-plan.md — "immutable
wheel/container builds"). `create_app()` requires a `manifest_path` argument
(docs/api/rest.md — bare `uvicorn --factory` mode doesn't work); this is the
one-line wrapper that document already tells any deployer to write, made
configurable via `MRAG_MANIFEST_PATH` so the same image works with any
manifest mounted or baked in, instead of hardcoding one path into the image.

Run with: uvicorn server:app --host 0.0.0.0 --port 8000
(the Dockerfile's CMD does exactly this, from /app/docker/).
"""
from __future__ import annotations

import os

from modular_rag.adapters.auth.keycloak_verifier import KeycloakTokenVerifier
from modular_rag.api import create_app

_MANIFEST_PATH = os.environ.get(
    "MRAG_MANIFEST_PATH", "manifests/presets/local-hybrid-rag.yaml"
)
_OIDC_ISSUER = os.environ.get("MRAG_OIDC_ISSUER_URL")
_OIDC_AUDIENCE = os.environ.get("MRAG_OIDC_AUDIENCE")

if bool(_OIDC_ISSUER) != bool(_OIDC_AUDIENCE):
    raise RuntimeError(
        "MRAG_OIDC_ISSUER_URL and MRAG_OIDC_AUDIENCE must be set together."
    )

_TOKEN_VERIFIER = (
    KeycloakTokenVerifier(issuer_url=_OIDC_ISSUER, audience=_OIDC_AUDIENCE)
    if _OIDC_ISSUER and _OIDC_AUDIENCE
    else None
)

app = create_app(_MANIFEST_PATH, token_verifier=_TOKEN_VERIFIER)
