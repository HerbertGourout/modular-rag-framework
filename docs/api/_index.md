# API — Overview

The framework exposes two user-facing surfaces over the same application/composition layer: a
CLI (`mrag`, described in [CLAUDE.md](../../CLAUDE.md)) for scriptable command-line use, and
a FastAPI REST API for integration into a third-party application (frontend, client backend
service, chatbot). Both use `ApplicationService` and honor the manifest-selected `DocumentEngine`
for answers. Ingestion and retrieval-only operations remain native application use cases.

**Why a REST API rather than just a Python library?** Many clients already have an
application (internal portal, Teams/Slack chatbot, existing backend) and want to call the
RAG pipeline as a service, without embedding heavy Python dependencies
(sentence-transformers, qdrant-client) into their own application stack.

- [rest.md](rest.md) — complete reference for the endpoints (`/health`, `/ready`, `/answer`,
  `/retrieve`), request/response schemas, error codes, Python and `curl` examples.

The API has built-in authentication: `create_app(..., token_verifier=...)` (Lot 16a) requires a
valid `Authorization: Bearer <token>` header on `/answer`/`/retrieve` when configured, verified
by `adapters/auth/keycloak_verifier.py`'s `KeycloakTokenVerifier` (Lot 11b) or any
`contracts.identity.TokenVerifier` implementation. It is optional only for a manifest with no
`governance.tenant_policy` wired (unauthenticated local/dev use); for a manifest that does wire
one, `token_verifier` is effectively mandatory — `create_app()` refuses to start without it
(Lot 1, tenant fail-closed). See the "Authentication" section of [rest.md](rest.md) for the full
behavior.
